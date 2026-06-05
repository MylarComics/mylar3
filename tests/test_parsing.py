import pytest
import csv
import re
from pathlib import Path
from typing import Optional
from app.services.parsing import parse_filename

def none_string_to_none(input_val: str) -> Optional[str]:
    return None if input_val == 'None' or input_val == '' else input_val

def unescape_unicode(text: str) -> Optional[str]:
    if text is None:
        return None
    # Replace unicode escape sequences like \u221e with their actual characters
    return re.sub(
        r'\\u([0-9a-fA-F]{4})',
        lambda m: chr(int(m.group(1), 16)),
        text
    )

def load_filename_parsing_tests():
    # Path to legacy filename_tests.csv
    test_csv_path = Path(__file__).parent.parent / ".old" / "tests" / "data" / "filename_tests.csv"
    
    test_list = []
    entry_counter = 0
    
    with open(test_csv_path, encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')

        for entry in reader:
            entry_counter += 1
            filename = unescape_unicode(entry['filename'])
            test_id = f"{entry_counter:03}:{filename}"
            
            xfail_bool = (entry['xfail'].lower() == "true")
            marks = [pytest.mark.xfail(reason=entry.get('testnotes', ''), strict=False)] if xfail_bool else []
            
            test_list.append(
                pytest.param(
                    filename, 
                    unescape_unicode(entry['series']), 
                    none_string_to_none(unescape_unicode(entry['issue'])),
                    none_string_to_none(unescape_unicode(entry['year'])), 
                    none_string_to_none(unescape_unicode(entry['volume'])),
                    xfail_bool,
                    id=test_id,
                    marks=marks
                )
            )
    return test_list

@pytest.mark.parametrize("filename,series,issue,year,volume,xfail", load_filename_parsing_tests())
def test_modern_filename_parsing(filename, series, issue, year, volume, xfail):
    parsed = parse_filename(filename, zero_padding=3 if (volume and 'v' in volume) or (issue and len(issue) >= 3) else 0)
    
    parsed_series = parsed['series_name'].lower() if parsed['series_name'] else ""
    parsed_vol = parsed['series_volume']
    parsed_year = parsed['issue_year']
    parsed_issue = parsed['issue_number']

    expected_series = series.lower()
    expected_vol = volume
    expected_year = year
    expected_issue = issue

    # Helper function to normalize naming/volume shapes for comparison
    actual = (
        parsed_series,
        None if expected_vol is None else parsed_vol,
        None if expected_year is None else parsed_year,
        None if expected_issue is None else parsed_issue
    )
    
    expected = (
        expected_series,
        expected_vol,
        expected_year,
        expected_issue
    )
    
    assert actual == expected
