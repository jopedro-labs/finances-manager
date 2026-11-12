"""Constants and mapping dictionaries for country aliases and data normalization."""

from __future__ import annotations

COUNTRY_ALIASES: dict[str, str] = {
    # United States
    "EUA": "United States",
    "USA": "United States",
    "US": "United States",
    "U.S.": "United States",
    "UNITED STATES": "United States",
    "UNITED STATES OF AMERICA": "United States",
    # United Kingdom / Great Britain
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "UNITED KINGDOM": "United Kingdom",
    "GREAT BRITAIN": "United Kingdom",
    "BRITAIN": "United Kingdom",
    "ENGLAND": "United Kingdom",
    "GB": "United Kingdom",
    # Netherlands / Holland
    "NETHERLANDS": "Netherlands",
    "THE NETHERLANDS": "Netherlands",
    "HOLLAND": "Netherlands",
    "NL": "Netherlands",
    # Switzerland
    "SWITZERLAND": "Switzerland",
    "SWISS CONFEDERATION": "Switzerland",
    "CH": "Switzerland",
    # Germany
    "GERMANY": "Germany",
    "DEUTSCHLAND": "Germany",
    "FEDERAL REPUBLIC OF GERMANY": "Germany",
    "DE": "Germany",
    # France
    "FRANCE": "France",
    "FR": "France",
    # Ireland
    "IRELAND": "Ireland",
    "REPUBLIC OF IRELAND": "Ireland",
    "IE": "Ireland",
    # Canada
    "CANADA": "Canada",
    "CA": "Canada",
    # Australia
    "AUSTRALIA": "Australia",
    "COMMONWEALTH OF AUSTRALIA": "Australia",
    "AU": "Australia",
    # Japan
    "JAPAN": "Japan",
    "JP": "Japan",
    # China
    "CHINA": "China",
    "PEOPLE'S REPUBLIC OF CHINA": "China",
    "PRC": "China",
    "CN": "China",
    # Taiwan
    "TAIWAN": "Taiwan",
    "TAIWAN, PROVINCE OF CHINA": "Taiwan",
    "REPUBLIC OF CHINA": "Taiwan",
    "TW": "Taiwan",
    # South Korea
    "SOUTH KOREA": "South Korea",
    "KOREA, REPUBLIC OF": "South Korea",
    "KOREA": "South Korea",
    "KR": "South Korea",
    # Singapore
    "SINGAPORE": "Singapore",
    "SG": "Singapore",
    # Hong Kong
    "HONG KONG": "Hong Kong",
    "HONG KONG SAR": "Hong Kong",
    "HK": "Hong Kong",
    # Sweden
    "SWEDEN": "Sweden",
    "SE": "Sweden",
    # Norway
    "NORWAY": "Norway",
    "NO": "Norway",
    # Denmark
    "DENMARK": "Denmark",
    "DK": "Denmark",
    # Finland
    "FINLAND": "Finland",
    "FI": "Finland",
    # Spain
    "SPAIN": "Spain",
    "ES": "Spain",
    # Italy
    "ITALY": "Italy",
    "IT": "Italy",
}
