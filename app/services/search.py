import asyncio
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import httpx
from pydantic import BaseModel
from app.core.config import settings
from app.core.logger import logger
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.parsing import parse_filename

class SearchResultItem(BaseModel):
    title: str
    download_url: str
    size: int  # In bytes
    provider_name: str
    type: str  # "nzb" or "torrent"
    published_date: Optional[str] = None

class IndexerConfig(BaseModel):
    name: str
    url: str
    apikey: str
    type: str  # "newznab" or "torznab"

def parse_providers_string(providers_str: str, provider_type: str) -> List[IndexerConfig]:
    """
    Parse a string of providers formatted as Name|URL|APIKey,Name2|URL2|APIKey2
    """
    providers = []
    if not providers_str or not providers_str.strip():
        return providers

    entries = providers_str.split(",")
    for entry in entries:
        parts = entry.split("|")
        if len(parts) == 3:
            name, url, apikey = parts
            providers.append(
                IndexerConfig(
                    name=name.strip(),
                    url=url.strip().rstrip("/"),
                    apikey=apikey.strip(),
                    type=provider_type
                )
            )
    return providers

def get_all_indexers() -> List[IndexerConfig]:
    """
    Get configured Newznab and Torznab indexers from Settings.
    """
    newznabs = parse_providers_string(settings.NEWZNAB_PROVIDERS, "newznab")
    torznabs = parse_providers_string(settings.TORZNAB_PROVIDERS, "torznab")
    return newznabs + torznabs

def generate_search_queries(series_name: str, issue_number: str) -> List[str]:
    """
    Generate query variations including standard space padding (e.g. 01, 001) for issue numbers.
    """
    # Clean the series name (e.g., removing slashes)
    clean_series = re.sub(r'[\/]', ' ', series_name).strip()
    queries = []

    # 1. Base query
    queries.append(f"{clean_series} {issue_number}")

    # 2. Padded queries if starting with a number
    match = re.match(r'^(\d+)(.*)$', issue_number)
    if match:
        num_str, suffix = match.groups()
        num_val = int(num_str)
        queries.append(f"{clean_series} {num_val:02d}{suffix}")
        queries.append(f"{clean_series} {num_val:03d}{suffix}")

    # Deduplicate while preserving order
    return list(dict.fromkeys(queries))

def parse_xml_results(xml_content: bytes, provider: IndexerConfig) -> List[SearchResultItem]:
    """
    Parse Newznab or Torznab RSS XML results using Python's ElementTree.
    """
    items = []
    try:
        root = ET.fromstring(xml_content)
    except Exception as e:
        logger.error(f"[Search] Failed to parse XML response from {provider.name}: {e}")
        return items

    namespaces = {
        'newznab': 'http://www.newznab.com/DTD/2010/feeds/attributes/',
        'torznab': 'http://torznab.com/schemas/2015/feed'
    }

    # Find all <item> tags
    channel = root.find('channel')
    item_nodes = channel.findall('item') if channel is not None else root.findall('.//item')

    for item_node in item_nodes:
        title_node = item_node.find('title')
        link_node = item_node.find('link')
        enclosure_node = item_node.find('enclosure')
        pubdate_node = item_node.find('pubDate')

        title = title_node.text.strip() if title_node is not None and title_node.text else ""
        if not title:
            continue

        # Extract download URL from enclosure first, fallback to link
        download_url = ""
        if enclosure_node is not None:
            download_url = enclosure_node.get('url', '')
        if not download_url and link_node is not None:
            download_url = link_node.text.strip() if link_node.text else ""

        if not download_url:
            continue

        # Extract size in bytes
        size = 0
        if enclosure_node is not None and enclosure_node.get('length'):
            try:
                size = int(enclosure_node.get('length', '0'))
            except ValueError:
                pass

        # If size is still 0, look for newznab or torznab namespace attributes
        if size == 0:
            for ns_prefix in ['newznab', 'torznab']:
                ns_uri = namespaces[ns_prefix]
                attr_nodes = item_node.findall(f'{{{ns_uri}}}attr')
                for attr_node in attr_nodes:
                    if attr_node.get('name') == 'size':
                        try:
                            size = int(attr_node.get('value', '0'))
                            break
                        except ValueError:
                            pass

        pub_date = pubdate_node.text.strip() if pubdate_node is not None and pubdate_node.text else None

        items.append(
            SearchResultItem(
                title=title,
                download_url=download_url,
                size=size,
                provider_name=provider.name,
                type="nzb" if provider.type == "newznab" else "torrent",
                published_date=pub_date
            )
        )
    return items

async def query_indexer(
    client: httpx.AsyncClient,
    provider: IndexerConfig,
    query: str,
    categories: str = "7030,8020"
) -> List[SearchResultItem]:
    """
    Sends a query request to a single indexer and returns the parsed SearchResultItems.
    """
    params = {
        "apikey": provider.apikey,
        "t": "search",
        "q": query,
        "cat": categories
    }
    url = f"{provider.url}/api"
    logger.fdebug(f"[Search] Querying provider {provider.name} at {url} for query '{query}'")

    try:
        # Respect verify settings
        response = await client.get(url, params=params, verify=settings.CV_VERIFY, timeout=15.0)
        if response.status_code == 200:
            return parse_xml_results(response.content, provider)
        logger.warning(f"[Search] Provider {provider.name} returned HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"[Search] Error querying provider {provider.name}: {e}")
    return []

def normalize_string(val: str) -> str:
    """
    Lowercase, remove spaces and non-alphanumeric chars for easy matching comparisons.
    """
    return re.sub(r'[^a-z0-9]', '', val.lower())

def is_title_match(parsed_title: Dict[str, Any], comic: Comic, issue: Issue) -> bool:
    """
    Validate if parsed release title matches target Comic and Issue parameters.
    """
    # 1. Compare Series Name (fuzzy comparison)
    parsed_series = normalize_string(parsed_title.get("series_name", ""))
    target_series = normalize_string(comic.comic_name)
    if parsed_series != target_series:
        # Try checking with start year removed from target if present
        target_series_no_year = re.sub(rf'{comic.comic_year}$', '', target_series).strip()
        if parsed_series != target_series_no_year:
            return False

    # 2. Compare Issue Number (normalize paddings)
    parsed_issue = parsed_title.get("issue_number")
    target_issue = issue.issue_number
    if not parsed_issue or not target_issue:
        return False

    try:
        # If both can be float, compare float values
        if float(parsed_issue) != float(target_issue):
            return False
    except ValueError:
        # Standard fallback string comparison (lowercase)
        if parsed_issue.lower().strip() != target_issue.lower().strip():
            return False

    # 3. Compare Year (if present in parsed release name)
    parsed_year = parsed_title.get("issue_year")
    if parsed_year and comic.comic_year:
        try:
            if int(parsed_year) != int(comic.comic_year):
                return False
        except ValueError:
            pass

    return True

async def search_issue(comic: Comic, issue: Issue) -> List[SearchResultItem]:
    """
    Concurrently search Newznab and Torznab indexers for a specific issue.
    Runs validation filtering on title strings using parsing.py.
    """
    indexers = get_all_indexers()
    if not indexers:
        logger.warning("[Search] No search providers/indexers are configured.")
        return []

    # Generate query strings
    queries = generate_search_queries(comic.comic_name, issue.issue_number)
    
    # We query all indexers and queries concurrently
    matched_results: List[SearchResultItem] = []
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        tasks = []
        for indexer in indexers:
            for q in queries:
                tasks.append(query_indexer(client, indexer, q))
                
        results_list = await asyncio.gather(*tasks)
        
        # Flatten the list of lists
        candidates = [item for sublist in results_list for item in sublist]
        
        # Validate and match titles
        seen_urls = set()
        for candidate in candidates:
            if candidate.download_url in seen_urls:
                continue
            # Parse the release name using our modernized parser
            parsed = parse_filename(candidate.title)
            if is_title_match(parsed, comic, issue):
                seen_urls.add(candidate.download_url)
                matched_results.append(candidate)
                
    # Sort matches by file size (largest first) to prioritize higher-quality releases
    matched_results.sort(key=lambda x: x.size, reverse=True)
    return matched_results

async def check_indexer(url: str, apikey: str) -> bool:
    """
    Verify if the indexer is online and responding to cap queries.
    """
    params = {
        "apikey": apikey,
        "t": "caps"
    }
    api_url = f"{url.rstrip('/')}/api"
    logger.info(f"[Search] Running capability diagnostic check for {api_url}")
    
    try:
        async with httpx.AsyncClient(verify=settings.CV_VERIFY, timeout=10.0) as client:
            response = await client.get(api_url, params=params)
            if response.status_code == 200:
                # Basic validation that it returns XML capabilities
                if b"<caps>" in response.content or b"<error" in response.content:
                    logger.info(f"[Search] Indexer diagnostic check successful for {api_url}")
                    return True
            logger.warning(f"[Search] Indexer check returned status code {response.status_code} for {api_url}")
    except Exception as e:
        logger.error(f"[Search] Indexer diagnostic check failed for {api_url}: {e}")
    return False
