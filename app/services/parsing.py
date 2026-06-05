import re
import unicodedata
from typing import Dict, Any, List, Optional
from app.core.logger import logger

# Mylar legacy exceptions list
ISSUE_EXCEPTIONS = {'mu', 'bey', 'alpha', 'omega', 'x', 'deaths', 'au', 'infinity', 'fcbd', 'special', 'annual', 'dc'}

# Legacy translation dictionary
LATIN_TRANSLATIONS = {
    0xc0: 'A', 0xc1: 'A', 0xc2: 'A', 0xc3: 'A', 0xc4: 'A', 0xc5: 'A',
    0xc6: 'Ae', 0xc7: 'C',
    0xc8: 'E', 0xc9: 'E', 0xca: 'E', 0xcb: 'E', 0x86: 'e',
    0xcc: 'I', 0xcd: 'I', 0xce: 'I', 0xcf: 'I',
    0xd0: 'Th', 0xd1: 'N',
    0xd2: 'O', 0xd3: 'O', 0xd4: 'O', 0xd5: 'O', 0xd6: 'O', 0xd8: 'O',
    0xd9: 'U', 0xda: 'U', 0xdb: 'U', 0xdc: 'U',
    0xdd: 'Y', 0xde: 'th', 0xdf: 'ss',
    0xe0: 'a', 0xe1: 'a', 0xe2: 'a', 0xe3: 'a', 0xe4: 'a', 0xe5: 'a',
    0xe6: 'ae', 0xe7: 'c',
    0xe8: 'e', 0xe9: 'e', 0xea: 'e', 0xeb: 'e', 0x0259: 'e',
    0xec: 'i', 0xed: 'i', 0xee: 'i', 0xef: 'i',
    0xf0: 'th', 0xf1: 'n',
    0xf2: 'o', 0xf3: 'o', 0xf4: 'o', 0xf5: 'o', 0xf6: 'o', 0xf8: 'o',
    0xf9: 'u', 0xfa: 'u', 0xfb: 'u', 0xfc: 'u',
    0xfd: 'y', 0xfe: 'th', 0xff: 'y',
    0xa1: '!', 0xa2: '{cent}', 0xa3: '{pound}', 0xa4: '{currency}',
    0xa5: '{yen}', 0xa6: '|', 0xa7: '{section}', 0xa8: '{umlaut}',
    0xa9: '{C}', 0xaa: '{^a}', 0xab: '<<', 0xac: '{not}',
    0xad: '-', 0xae: '{R}', 0xaf: '_', 0xb0: '{degrees}',
    0xb1: '{+/-}', 0xb2: '{^2}', 0xb3: '{^3}', 0xb4: "'",
    0xb5: '{micro}', 0xb6: '{paragraph}', 0xb7: '*', 0xb8: '{cedilla}',
    0xb9: '{^1}', 0xba: '{^o}', 0xbb: '>>',
    0xbc: '{1/4}', 0xbd: '{1/2}', 0xbe: '{3/4}', 0xbf: '?',
    0xd7: '*', 0xf7: '/'
}

def latin_to_ascii(text: str) -> str:
    result = ''
    for char in text:
        val = ord(char)
        if val in LATIN_TRANSLATIONS:
            result += LATIN_TRANSLATIONS[val]
        elif val >= 0x80:
            pass
        else:
            result += char
    return result

def clean_name(name: str) -> str:
    pass1 = latin_to_ascii(name).lower()
    cleaned = re.sub(r'[\/\@\#\$\%\^\*\+\"\[\]\{\}\<\>\=\_]', ' ', pass1)
    return cleaned

def is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False

# Rippers and metadata tags to filter
RIP_GROUPS = [
    '-empire', '-empire-hd', 'minutemen-', '-dcp', 'Glorith-HD',
    'OkC.O.M.P.U.T.O.-Novus', 'TLK-EMPIRE-HD', 'Oracle-SWA',
    'Minutemen-Thoth', 'Zone-Empire', 'Glorith', 'flattermann', 'Steam-DCP',
    'digital', 'Minutemen-DizzynTheRain'
]

def parse_filename(filename: str, zero_padding: int = 0) -> Dict[str, Any]:
    logger.fdebug(f"Parsing filename: {filename}")

    # 1. Clean file extension
    comic_exts = ('.cbr', '.cbz', '.cb7', '.pdf')
    filetype = 'unknown'
    mod_filename = filename
    for ext in comic_exts:
        if filename.lower().endswith(ext):
            filetype = ext
            mod_filename = filename[:-len(ext)]
            break

    # 2. Extract scan group/rippers
    scangroup = None
    all_rippers = sorted(RIP_GROUPS, key=len, reverse=True)
    for rp in all_rippers:
        match = re.search(r'[\(\[\s_-]' + re.escape(rp) + r'[\)\]\s_-]', mod_filename, re.IGNORECASE)
        if match:
            scangroup = rp
            mod_filename = mod_filename.replace(match.group(0), ' ').strip()
        elif rp.lower() in mod_filename.lower():
            scangroup = rp
            mod_filename = re.sub(re.escape(rp), '', mod_filename, flags=re.IGNORECASE)

    # 3. Handle Mylar's unique replacements
    mod_filename = re.sub(r'\+', 'c11', mod_filename)
    mod_filename = re.sub(r'\&', 'f11', mod_filename)
    mod_filename = re.sub(r'\'', 'g11', mod_filename)
    mod_filename = re.sub(r'\@', 'h11', mod_filename)

    # Clean dots: protect decimal issue numbers, and replace spacer dots with spaces
    # Allow any number of decimal places (e.g. .0001 or .1) but do not protect if the digits after the dot are a year
    mod_filename = re.sub(r'\b(?!19\d{2}|20[0-2]\d|2030)(\d{1,3})\.(?!(?:19\d{2}|20[0-2]\d|2030)(?!\d))(\d+)(?!\d)', r'\1_DECIMAL_\2', mod_filename)
    mod_filename = mod_filename.replace('.', ' ')
    mod_filename = mod_filename.replace('_DECIMAL_', '.')

    # 4. Tokenize using regex supporting fractions and infinity
    tokens = re.findall(
        r'(?imu)\([\w\s-]+\)|[-+]?\d*\.\d+|\d+[\s]COVERS+|\d+[(\s|\-)]PAGE+|\d{4}-\d{2}-\d{2}|\d+[(th|nd|rd|st)]+|[\(^\)+]|\[.*?\]|\d+|[\w\u2019\'¢½¼¾∞-]+|#?\d\.\d+|#[\.-]\w+|#[\d*\.\d+|\w+\d+½¼¾∞]+|#(?<![\w\d])XCV(?![\w\d])+|#[\w+]|\)',
        mod_filename,
        re.UNICODE
    )
    tokens = [t.strip() for t in tokens if t.strip()]

    # Normalize tokens using legacy clean-up loop
    spf = []
    mini = False
    for idx, x in enumerate(tokens):
        if x == 'of':
            if idx > 0 and tokens[idx-1].isdigit():
                mini = True
                spf.append(x)
                continue
        if mini is True:
            mini = False
            try:
                if x.lower() == 'infinity':
                    raise Exception
                if x.isdigit() or is_number(x):
                    spf.append(f'(of {x})')
                else:
                    spf.append(x)
            except Exception:
                spf.append(x)
        elif x in (')', '('):
            pass
        elif x in ('p', 'ctc', 'px'):
            try:
                if spf and spf[-1].isdigit():
                    spf[-1] = f"{spf[-1]}{x}"
                elif spf and spf[-1].endswith('p') and spf[-1][:-1].isdigit() and x == 'ctc':
                    spf[-1] = f"{spf[-1]}{x}"
                else:
                    spf.append(x)
            except Exception:
                spf.append(x)
        else:
            spf.append(x)
    tokens = spf

    # Protect the first token if it is part of a "2000 AD" series name
    protect_first_token = False
    if len(tokens) > 1 and tokens[0].isdigit() and len(tokens[0]) == 4:
        if tokens[1].lower() == 'ad':
            protect_first_token = True
        elif len(tokens) > 2 and tokens[1].lower() == 'a' and tokens[2].lower() == 'd':
            protect_first_token = True

    # 5. Extract year and volume.
    issue_year = None
    year_pos = -1
    for idx in range(len(tokens) - 1, -1, -1):
        if idx == 0 and protect_first_token:
            continue

        token = tokens[idx]
        cleaned_token = re.sub(r'^[^a-zA-Z0-9#½¼¾∞\u2019\'-]+|[^a-zA-Z0-9#½¼¾∞\u2019\'-]+$', '', token).strip()

        # Check for full dates YYYY-MM-DD or MM-YYYY
        full_date_match = re.search(r'\b(19\d{2}|20[0-2]\d|2030)-(0\d|1[0-2])-(0\d|[12]\d|3[01])\b', cleaned_token)
        month_year_match = re.search(r'\b(0\d|1[0-2])-(19\d{2}|20[0-2]\d|2030)\b', cleaned_token)
        
        year_val = None
        if full_date_match:
            year_val = int(full_date_match.group(1))
        elif month_year_match:
            year_val = int(month_year_match.group(2))
        else:
            year_match = re.search(r'\b(19\d{2}|20[0-2]\d|2030)\b', cleaned_token)
            if year_match:
                year_val = int(year_match.group(1))

        if year_val is not None:
            # Check if followed by AD
            is_ad = False
            if idx + 1 < len(tokens):
                next_tok = tokens[idx + 1].lower()
                if next_tok in ('ad', 'a', 'd'):
                    is_ad = True

            import datetime
            current_year = datetime.datetime.now().year
            if year_val > current_year + 1:
                continue

            if not is_ad:
                if full_date_match or month_year_match or token.startswith('(') or token.startswith('{') or token.startswith('['):
                    issue_year = str(year_val)
                    year_pos = idx
                    break
                else:
                    # Count numeric tokens to avoid stealing issue number
                    numeric_tokens = []
                    for t in tokens:
                        c_t = re.sub(r'^[^a-zA-Z0-9#½¼¾∞\u2019\'-]+|[^a-zA-Z0-9#½¼¾∞\u2019\'-]+$', '', t).strip()
                        if is_number(c_t) or c_t.startswith('#'):
                            numeric_tokens.append(c_t)
                    
                    if len(numeric_tokens) <= 1:
                        continue
                    
                    issue_year = str(year_val)
                    year_pos = idx
                    break

    # Extract Volume
    series_volume = None
    vol_pos = -1
    for idx in range(len(tokens) - 1, -1, -1):
        token = tokens[idx]
        cleaned_token = re.sub(r'^[^a-zA-Z0-9#½¼¾∞\u2019\'-]+|[^a-zA-Z0-9#½¼¾∞\u2019\'-]+$', '', token).strip()
        
        # Case 1: Combined volume like "v3" or "Vol.1" (only digits, no roman numerals or words)
        vol_match = re.match(r'^(v|vol|volume)\.?\s*(\d+)$', cleaned_token, re.IGNORECASE)
        if vol_match:
            vol_num = vol_match.group(2)
            series_volume = f"v{vol_num.lower()}"
            vol_pos = idx
            break
            
        # Case 2: Separate tokens like "Vol." followed by "01"
        if cleaned_token.lower() in ('v', 'vol', 'volume'):
            if idx + 1 < len(tokens):
                next_tok = re.sub(r'^[^a-zA-Z0-9#½¼¾∞\u2019\'-]+|[^a-zA-Z0-9#½¼¾∞\u2019\'-]+$', '', tokens[idx + 1]).strip()
                if next_tok.isdigit():
                    series_volume = f"v{next_tok.lower()}"
                    vol_pos = idx
                    break

    # 6. Extract Issue Number
    issue_number = None
    issue_pos = -1

    for idx in range(len(tokens) - 1, -1, -1):
        if idx == 0 and protect_first_token:
            continue

        # Skip year and volume positions if we are inspecting them
        if idx == year_pos or idx == vol_pos or (vol_pos != -1 and idx == vol_pos + 1 and tokens[vol_pos].lower() in ('v', 'vol', 'volume')):
            continue

        token = tokens[idx]
        cleaned_token = re.sub(r'^[^a-zA-Z0-9#½¼¾∞\u2019\'-]+|[^a-zA-Z0-9#½¼¾∞\u2019\'-]+$', '', token).strip()

        # Ignore metadata and page counts
        if cleaned_token.lower() in ('digital', 'c2c', 'web', 'covers', 'repack', 'variant', 'ctc'):
            continue
            
        if re.search(r'\b\d+(p|page|pages|covers)\b', cleaned_token, re.IGNORECASE):
            continue

        is_numeric_issue = False
        if token.startswith('#'):
            is_numeric_issue = True
        elif is_number(cleaned_token):
            is_numeric_issue = True
        elif any(f_char in cleaned_token for f_char in ('½', '¼', '¾', '∞')):
            is_numeric_issue = True
        elif re.fullmatch(r'\d+[\/\-]\d+', cleaned_token):
            is_numeric_issue = True

        if is_numeric_issue:
            if cleaned_token.startswith('#'):
                cleaned_token = cleaned_token[1:]
            issue_number = cleaned_token
            issue_pos = idx
            
            # Check if followed by an exception word
            if idx + 1 < len(tokens):
                next_tok = re.sub(r'^[^a-zA-Z0-9#½¼¾∞\u2019\'-]+|[^a-zA-Z0-9#½¼¾∞\u2019\'-]+$', '', tokens[idx + 1]).strip()
                if next_tok.lower() in ISSUE_EXCEPTIONS:
                    issue_number = f"{issue_number} {next_tok}"
            break

    # Second pass fallback
    if issue_number is None:
        for idx in range(len(tokens) - 1, -1, -1):
            if idx == 0 and protect_first_token:
                continue

            if idx == year_pos or idx == vol_pos or (vol_pos != -1 and idx == vol_pos + 1 and tokens[vol_pos].lower() in ('v', 'vol', 'volume')):
                continue

            token = tokens[idx]
            cleaned_token = re.sub(r'^[^a-zA-Z0-9#½¼¾∞\u2019\'-]+|[^a-zA-Z0-9#½¼¾∞\u2019\'-]+$', '', token).strip()

            if cleaned_token.lower() in ('digital', 'c2c', 'web', 'covers', 'repack', 'variant', 'ctc'):
                continue
            if re.search(r'\b\d+(p|page|pages|covers)\b', cleaned_token, re.IGNORECASE):
                continue

            if cleaned_token.lower() in ISSUE_EXCEPTIONS or re.fullmatch(r'\d+[a-zA-Z]+', cleaned_token) or re.fullmatch(r'[a-zA-Z]+-\d+', cleaned_token):
                issue_number = cleaned_token
                issue_pos = idx
                break

    # Swap 2000 AD Year and Issue if issue is None
    if issue_number is None and issue_year is not None and '2000ad' in filename.lower().replace(' ', '').replace('.', ''):
        issue_number = issue_year
        issue_year = None
        # Adjust issue_pos to the year position for proper slicing
        issue_pos = year_pos
        year_pos = -1

    # 7. Construct Series Name by slicing using the boundary position
    start_pos = 0
    if year_pos == 0:
        start_pos = 1

    end_pos = len(tokens)
    if year_pos != -1 and year_pos != 0:
        end_pos = min(end_pos, year_pos)
    if vol_pos != -1:
        end_pos = min(end_pos, vol_pos)
    if issue_pos != -1:
        end_pos = min(end_pos, issue_pos)

    series_tokens = tokens[start_pos:end_pos]
    while series_tokens and series_tokens[-1] == '-':
        series_tokens.pop()

    final_series_tokens = []
    for tok in series_tokens:
        cleaned_tok = re.sub(r'^[^a-zA-Z0-9#½¼¾∞\u2019\'-]+|[^a-zA-Z0-9#½¼¾∞\u2019\'-]+$', '', tok).strip()
        if cleaned_tok.lower() in ('digital', 'c2c', 'web', 'covers', 'repack', 'variant'):
            continue
        final_series_tokens.append(tok)

    series_name = " ".join(final_series_tokens)

    # Restore unique delimiters
    series_name = re.sub('c11', '+', series_name)
    series_name = re.sub('f11', '&', series_name)
    series_name = re.sub('g11', '\'', series_name)
    series_name = re.sub('h11', '@', series_name)

    if issue_number:
        issue_number = re.sub('c11', '+', issue_number)
        issue_number = re.sub('f11', '&', issue_number)
        issue_number = re.sub('g11', '\'', issue_number)
        issue_number = re.sub('h11', '@', issue_number)

    # Clean punctuation and trailing separators
    series_name = re.sub(r'\s+', ' ', series_name).strip()
    if series_name.endswith('-'):
        series_name = series_name[:-1].strip()
    if series_name.endswith(':'):
        series_name = series_name[:-1].strip()
    if series_name.startswith('-'):
        series_name = series_name[1:].strip()

    # Clean spaces around hyphens
    series_name = re.sub(r'\s+-\s+', ' - ', series_name)

    series_name_decoded = unicodedata.normalize('NFKD', series_name)

    booktype = 'issue'
    if issue_number is None:
        booktype = 'TPB/GN/HC/One-Shot'
        if series_volume is None:
            series_volume = 'v1'

    return {
        'parse_status': 'success' if series_name else 'failure',
        'sub': None,
        'comicfilename': filename,
        'comiclocation': None,
        'series_name': series_name,
        'series_name_decoded': series_name_decoded,
        'issueid': None,
        'dynamic_name': series_name,
        'series_volume': series_volume,
        'alt_series': None,
        'alt_issue': None,
        'issue_year': issue_year,
        'issue_number': issue_number,
        'scangroup': scangroup,
        'reading_order': None,
        'booktype': booktype
    }
