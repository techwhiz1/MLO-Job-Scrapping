import asyncio
import json
import re
from typing import List, Dict, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlsplit, urlunsplit
import os
from datetime import datetime
import time
import logging
import aiohttp
import cssutils
from dotenv import load_dotenv

load_dotenv()

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from crawl4ai import AsyncWebCrawler
from openai import AsyncOpenAI
from bs4 import BeautifulSoup

# Suppress cssutils warnings
cssutils.log.setLevel(logging.CRITICAL)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobScraper:
    US_STATES = {
        "al": "Alabama", "alabama": "Alabama",
        "ak": "Alaska", "alaska": "Alaska",
        "az": "Arizona", "arizona": "Arizona",
        "ar": "Arkansas", "arkansas": "Arkansas",
        "ca": "California", "california": "California",
        "co": "Colorado", "colorado": "Colorado",
        "ct": "Connecticut", "connecticut": "Connecticut",
        "de": "Delaware", "delaware": "Delaware",
        "fl": "Florida", "florida": "Florida",
        "ga": "Georgia", "georgia": "Georgia",
        "hi": "Hawaii", "hawaii": "Hawaii",
        "id": "Idaho", "idaho": "Idaho",
        "il": "Illinois", "illinois": "Illinois",
        "in": "Indiana", "indiana": "Indiana",
        "ia": "Iowa", "iowa": "Iowa",
        "ks": "Kansas", "kansas": "Kansas",
        "ky": "Kentucky", "kentucky": "Kentucky",
        "la": "Louisiana", "louisiana": "Louisiana",
        "me": "Maine", "maine": "Maine",
        "md": "Maryland", "maryland": "Maryland",
        "ma": "Massachusetts", "massachusetts": "Massachusetts",
        "mi": "Michigan", "michigan": "Michigan",
        "mn": "Minnesota", "minnesota": "Minnesota",
        "ms": "Mississippi", "mississippi": "Mississippi",
        "mo": "Missouri", "missouri": "Missouri",
        "mt": "Montana", "montana": "Montana",
        "ne": "Nebraska", "nebraska": "Nebraska",
        "nv": "Nevada", "nevada": "Nevada",
        "nh": "New Hampshire", "new hampshire": "New Hampshire",
        "nj": "New Jersey", "new jersey": "New Jersey",
        "nm": "New Mexico", "new mexico": "New Mexico",
        "ny": "New York", "new york": "New York",
        "nc": "North Carolina", "north carolina": "North Carolina",
        "nd": "North Dakota", "north dakota": "North Dakota",
        "oh": "Ohio", "ohio": "Ohio",
        "ok": "Oklahoma", "oklahoma": "Oklahoma",
        "or": "Oregon", "oregon": "Oregon",
        "pa": "Pennsylvania", "pennsylvania": "Pennsylvania",
        "ri": "Rhode Island", "rhode island": "Rhode Island",
        "sc": "South Carolina", "south carolina": "South Carolina",
        "sd": "South Dakota", "south dakota": "South Dakota",
        "tn": "Tennessee", "tennessee": "Tennessee",
        "tx": "Texas", "texas": "Texas",
        "ut": "Utah", "utah": "Utah",
        "vt": "Vermont", "vermont": "Vermont",
        "va": "Virginia", "virginia": "Virginia",
        "wa": "Washington", "washington": "Washington",
        "wv": "West Virginia", "west virginia": "West Virginia",
        "wi": "Wisconsin", "wisconsin": "Wisconsin",
        "wy": "Wyoming", "wyoming": "Wyoming",
        "dc": "District of Columbia", "district of columbia": "District of Columbia",
        "washington dc": "District of Columbia",
    }
    CANADA_PROVINCES = {
        "ab": "Alberta", "alberta": "Alberta",
        "bc": "British Columbia", "b.c.": "British Columbia", "british columbia": "British Columbia",
        "mb": "Manitoba", "manitoba": "Manitoba",
        "nb": "New Brunswick", "new brunswick": "New Brunswick",
        "nl": "Newfoundland and Labrador", "newfoundland": "Newfoundland and Labrador",
        "newfoundland and labrador": "Newfoundland and Labrador",
        "ns": "Nova Scotia", "nova scotia": "Nova Scotia",
        "nt": "Northwest Territories", "northwest territories": "Northwest Territories",
        "nu": "Nunavut", "nunavut": "Nunavut",
        "on": "Ontario", "ontario": "Ontario",
        "pe": "Prince Edward Island", "pei": "Prince Edward Island",
        "prince edward island": "Prince Edward Island",
        "qc": "Quebec", "pq": "Quebec", "québec": "Quebec", "quebec": "Quebec",
        "sk": "Saskatchewan", "saskatchewan": "Saskatchewan",
        "yt": "Yukon", "yk": "Yukon", "yukon": "Yukon",
    }
    COUNTRY_ALIASES = {
        "ca": "Canada", "can": "Canada", "canada": "Canada",
        "us": "United States", "usa": "United States", "u.s.": "United States",
        "u.s.a.": "United States", "united states": "United States",
        "united states of america": "United States", "america": "United States",
    }
    CITY_LOCATION_HINTS = {
        "val-d'or": ("Val-d'Or", "Quebec", "Canada"),
        "val d'or": ("Val-d'Or", "Quebec", "Canada"),
        "toronto": ("Toronto", "Ontario", "Canada"),
        "vancouver": ("Vancouver", "British Columbia", "Canada"),
        "montreal": ("Montreal", "Quebec", "Canada"),
        "montréal": ("Montreal", "Quebec", "Canada"),
        "calgary": ("Calgary", "Alberta", "Canada"),
        "edmonton": ("Edmonton", "Alberta", "Canada"),
        "ottawa": ("Ottawa", "Ontario", "Canada"),
        "winnipeg": ("Winnipeg", "Manitoba", "Canada"),
        "halifax": ("Halifax", "Nova Scotia", "Canada"),
        "mississauga": ("Mississauga", "Ontario", "Canada"),
        "sudbury": ("Sudbury", "Ontario", "Canada"),
        "lively": ("Lively", "Ontario", "Canada"),
        "denver": ("Denver", "Colorado", "United States"),
        "boston": ("Boston", "Massachusetts", "United States"),
        "chicago": ("Chicago", "Illinois", "United States"),
        "houston": ("Houston", "Texas", "United States"),
        "phoenix": ("Phoenix", "Arizona", "United States"),
        "philadelphia": ("Philadelphia", "Pennsylvania", "United States"),
        "san antonio": ("San Antonio", "Texas", "United States"),
        "san diego": ("San Diego", "California", "United States"),
        "dallas": ("Dallas", "Texas", "United States"),
        "san jose": ("San Jose", "California", "United States"),
        "austin": ("Austin", "Texas", "United States"),
        "seattle": ("Seattle", "Washington", "United States"),
        "portland": ("Portland", "Oregon", "United States"),
        "nashville": ("Nashville", "Tennessee", "United States"),
        "oklahoma city": ("Oklahoma City", "Oklahoma", "United States"),
    }

    def __init__(
        self,
        filter_location: bool = False,
        include_html_content: bool = True,
        save_debug_html: Optional[bool] = None,
        fast_mode: bool = False,
        categories: Optional[List[Dict]] = None,
        country_and_states: Optional[List[Dict]] = None,
    ):
        # Set OpenAI API key
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # OpenAI client for AI extraction
        self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        
        self.include_html_content = include_html_content
        self.fast_mode = fast_mode
        self.categories = categories or []
        self.country_and_states = country_and_states or []
        self.save_debug_html = (
            save_debug_html
            if save_debug_html is not None
            else os.getenv("SAVE_DEBUG_HTML", "false").lower() == "true"
        )

        # Create debug directory only when debug snapshots are enabled.
        self.debug_dir = "debug_html"
        if self.save_debug_html and not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
        
        # Track scraped URLs to prevent duplicates
        self.scraped_urls = set()
        self.scraped_jobs = []  # Store successfully scraped jobs
        
        # Location filtering
        self.filter_location = filter_location

    def _selenium_http_timeout_seconds(self) -> int:
        """HTTP read timeout for chromedriver commands."""
        default_timeout = "60" if self.fast_mode else "120"
        return int(os.getenv("SELENIUM_HTTP_READ_TIMEOUT", default_timeout))

    def _selenium_page_load_timeout_seconds(self) -> int:
        return int(os.getenv("SELENIUM_PAGE_LOAD_TIMEOUT", "45"))

    def _selenium_script_timeout_seconds(self) -> int:
        return int(os.getenv("SELENIUM_SCRIPT_TIMEOUT", "120"))

    def _skip_main_document_scroll(self) -> bool:
        """Skip slow parent-page scrolling in API fast mode unless explicitly enabled."""
        value = os.getenv("SKIP_MAIN_DOCUMENT_SCROLL")
        if value is not None:
            return value.lower() in ("1", "true", "yes", "on")
        return self.fast_mode

    def _clean_location_part(self, value: str) -> str:
        value = re.sub(r"\s+", " ", str(value or "")).strip(" ,|-")
        value = re.sub(r"\b(?:remote|hybrid|onsite|on-site|full[- ]time|part[- ]time)\b", "", value, flags=re.I)
        value = re.sub(r"\s+", " ", value).strip(" ,|-")
        return value

    def _normalize_country_name(self, value: str) -> str:
        value = self._clean_location_part(value)
        return self.COUNTRY_ALIASES.get(value.lower().strip("."), value)

    def _normalize_state_name(self, value: str, country: str = "") -> str:
        value = self._clean_location_part(value)
        key = value.lower().strip(".")
        country_key = (country or "").lower()
        if country_key == "canada" or key in self.CANADA_PROVINCES:
            return self.CANADA_PROVINCES.get(key, value)
        if country_key == "united states" or key in self.US_STATES:
            return self.US_STATES.get(key, value)
        return value

    def _country_from_state(self, state: str) -> str:
        key = self._clean_location_part(state).lower().strip(".")
        if key in self.CANADA_PROVINCES or state in self.CANADA_PROVINCES.values():
            return "Canada"
        if key in self.US_STATES or state in self.US_STATES.values():
            return "United States"
        return ""

    def _infer_city_hint(self, city: str) -> Tuple[str, str, str]:
        key = self._clean_location_part(city).lower()
        return self.CITY_LOCATION_HINTS.get(key, ("", "", ""))

    def _country_state_id(self, row: Dict):
        return row.get("id")

    def _country_state_name(self, row: Dict) -> str:
        return str(row.get("name") or row.get("title") or row.get("label") or "")

    def _country_state_code(self, row: Dict) -> str:
        return str(row.get("code") or row.get("abbreviation") or "")

    def _country_state_parent_id(self, row: Dict):
        for key in ("parentId", "parent_id", "parentID", "parent"):
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    def _location_lookup_key(self, value: str) -> str:
        value = self._clean_location_part(value).lower()
        value = self.COUNTRY_ALIASES.get(value.strip("."), value)
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    def _match_country_state_ids(self, state_name: str, country_name: str) -> Tuple[object, object]:
        if not self.country_and_states:
            return None, None

        countries = [
            row for row in self.country_and_states
            if self._country_state_parent_id(row) in (None, "")
        ]
        states = [
            row for row in self.country_and_states
            if self._country_state_parent_id(row) not in (None, "")
        ]

        country_key = self._location_lookup_key(self._normalize_country_name(country_name))
        country_id = None
        if country_key:
            for country in countries:
                row_keys = {
                    self._location_lookup_key(self._country_state_name(country)),
                    self._location_lookup_key(self._country_state_code(country)),
                    self._location_lookup_key(self._normalize_country_name(self._country_state_code(country))),
                }
                if country_key in row_keys:
                    country_id = self._country_state_id(country)
                    break

        state_key = self._location_lookup_key(state_name)
        state_id = None
        if state_key:
            for state in states:
                if country_id is not None and str(self._country_state_parent_id(state)) != str(country_id):
                    continue
                row_keys = {
                    self._location_lookup_key(self._country_state_name(state)),
                    self._location_lookup_key(self._country_state_code(state)),
                }
                if state_key in row_keys:
                    state_id = self._country_state_id(state)
                    if country_id is None:
                        country_id = self._country_state_parent_id(state)
                    break

        return state_id, country_id

    def _standardize_location_fields(self, job_data: Dict) -> None:
        """
        Normalize location into city/town, province/state, country and expose
        separate city/state/country fields. Uses source/AI data first, then
        fills missing country/state from known state/province/city hints.
        """
        raw_location = self._clean_location_part(job_data.get("location", ""))
        city = self._clean_location_part(job_data.get("city", ""))
        state = self._clean_location_part(job_data.get("state", "") or job_data.get("province", ""))
        country = self._normalize_country_name(job_data.get("country", ""))

        location_without_postal = re.sub(
            r"\b[A-Z]\d[A-Z][ -]?\d[A-Z]\d\b|\b\d{5}(?:-\d{4})?\b",
            "",
            raw_location,
            flags=re.I,
        )
        parts = [
            self._clean_location_part(part)
            for part in re.split(r"\s*(?:,|\||/|\u2022| - )\s*", location_without_postal)
            if self._clean_location_part(part)
        ]

        if parts:
            last_country = self._normalize_country_name(parts[-1])
            if not country and last_country in ("Canada", "United States"):
                country = last_country
                parts = parts[:-1]

        if len(parts) >= 2:
            possible_state = self._normalize_state_name(parts[-1], country)
            if not state:
                state = possible_state
            if not city:
                city = parts[-2] if len(parts) > 2 and possible_state == parts[-1] else parts[0]
        elif len(parts) == 1:
            only_part = parts[0]
            normalized_state = self._normalize_state_name(only_part, country)
            inferred_country = self._country_from_state(normalized_state)
            if inferred_country and not state:
                state = normalized_state
            elif not city:
                city = only_part

        state = self._normalize_state_name(state, country)
        if not country:
            country = self._country_from_state(state)

        if city and (not state or not country):
            hint_city, hint_state, hint_country = self._infer_city_hint(city)
            if hint_city:
                city = hint_city
                state = state or hint_state
                country = country or hint_country

        if state and not country:
            country = self._country_from_state(state)

        standardized = ", ".join(part for part in (city, state, country) if part)
        state_id, country_id = self._match_country_state_ids(state, country)
        job_data["city"] = city
        job_data["state"] = state_id if state_id is not None else state
        job_data["country"] = country_id if country_id is not None else country
        job_data["location"] = standardized or raw_location

    def _category_id(self, category: Dict) -> str:
        for key in ("id", "categoryId", "category_id", "value", "uuid"):
            value = category.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _category_parent_id(self, category: Dict) -> str:
        for key in ("parent_category_id", "parentCategoryId", "parent_id", "parentId", "parent"):
            if key in category:
                value = category.get(key)
                if value not in (None, ""):
                    return str(value)
                return ""
        return ""

    def _category_has_parent(self, category: Dict) -> bool:
        for key in ("parent_category_id", "parentCategoryId", "parent_id", "parentId", "parent"):
            if key in category:
                value = category.get(key)
                return value not in (None, "")
        return False

    def _is_other_category(self, category: Dict) -> bool:
        return self._category_name(category).strip().lower() in ("other", "others")

    def _category_is_active(self, category: Dict) -> bool:
        for key in ("active", "isActive", "enabled", "isEnabled"):
            if key in category:
                value = category.get(key)
                if isinstance(value, str):
                    return value.strip().lower() not in ("false", "0", "no", "disabled")
                return bool(value)
        return True

    def _category_is_selectable_child(self, category: Dict) -> bool:
        if not self._category_id(category) or not self._category_is_active(category):
            return False
        return self._category_has_parent(category)

    def _category_sort_key(self, category: Dict) -> Tuple[int, str]:
        # Keep "Other" visible in the candidate list but place it last.
        return (1 if self._is_other_category(category) else 0, self._category_name(category).lower())

    def _category_name(self, category: Dict) -> str:
        for key in ("name", "title", "label", "category", "categoryName", "displayName", "slug"):
            value = category.get(key)
            if value:
                return str(value)
        return self._category_id(category)

    def _selectable_categories(self) -> List[Dict]:
        """
        Return only categories that can be assigned to a job.
        With parent_category_id tree data, this means leaf/child categories only.
        """
        if not self.categories:
            return []

        child_categories = sorted([
            category
            for category in self.categories
            if self._category_is_selectable_child(category)
        ], key=self._category_sort_key)

        # If the table has tree data, only child rows are valid choices.
        if child_categories:
            return child_categories

        return sorted(
            [
                category
                for category in self.categories
                if self._category_id(category) and self._category_is_active(category)
            ],
            key=self._category_sort_key,
        )

    def _category_parent_name(self, category: Dict) -> str:
        parent_id = self._category_parent_id(category)
        if not parent_id:
            return ""
        for possible_parent in self.categories:
            if self._category_id(possible_parent) == parent_id:
                return self._category_name(possible_parent)
        return ""

    def _other_category(self, categories: Optional[List[Dict]] = None) -> Optional[Dict]:
        categories = categories if categories is not None else self._selectable_categories()
        for category in categories:
            category_name = self._category_name(category).strip().lower()
            if category_name in ("other", "others"):
                return category
        return None

    def _named_category(self, names: Tuple[str, ...], categories: Optional[List[Dict]] = None) -> Optional[Dict]:
        categories = categories if categories is not None else self._selectable_categories()
        wanted = {name.strip().lower() for name in names}
        for category in categories:
            if self._category_name(category).strip().lower() in wanted:
                return category
        return None

    def _is_low_information_test_job(self, job_data: Dict) -> bool:
        text = " ".join(str(job_data.get(key, "")) for key in (
            "job_title",
            "job_description",
            "key_responsibilities",
            "qualifications_and_skills",
            "required_experience",
            "educational_level",
            "certification_level",
        )).lower()
        tokens = re.findall(r"[a-z0-9]+", text)
        if not tokens:
            return False
        noise_tokens = {
            "test", "testing", "tester", "sample", "dummy", "demo", "example",
            "asdf", "n/a", "na", "none", "null", "content", "title", "job",
        }
        meaningful_tokens = [token for token in tokens if token not in ("job", "title", "content")]
        if len(tokens) <= 8 and all(token in noise_tokens for token in tokens):
            return True
        return bool(meaningful_tokens) and len(meaningful_tokens) <= 4 and all(
            token in noise_tokens for token in meaningful_tokens
        )

    def _format_categories_for_prompt(self) -> str:
        selectable_categories = self._selectable_categories()
        if not selectable_categories:
            return "No child/leaf categories were provided. Return null for category_id and category_name."
        lines = []
        for category in selectable_categories:
            category_id = self._category_id(category)
            category_name = self._category_name(category)
            if category_id or category_name:
                parent_name = self._category_parent_name(category)
                parent_part = f"; parent: {parent_name}" if parent_name else ""
                lines.append(f"- id: {category_id}; name: {category_name}{parent_part}")
        if not lines:
            return "No child/leaf categories were provided. Return null for category_id and category_name."
        other_category = self._other_category(selectable_categories)
        suffix = ""
        if other_category:
            suffix = "\n\nOther is a valid child category candidate. Use Other when no specific child category matches."
        return "\n".join(lines) + suffix

    def _normalize_extracted_category(self, job_data: Dict) -> None:
        selectable_categories = self._selectable_categories()
        if not selectable_categories:
            job_data["category_id"] = ""
            job_data["category_name"] = ""
            return

        extracted_id = (job_data.get("category_id") or "").strip().lower()
        extracted_name = (job_data.get("category_name") or job_data.get("category") or "").strip().lower()

        if self._is_low_information_test_job(job_data):
            fallback_category = (
                self._named_category(("test", "testing"), selectable_categories)
                or self._other_category(selectable_categories)
            )
            if fallback_category:
                job_data["category_id"] = self._category_id(fallback_category)
                job_data["category_name"] = self._category_name(fallback_category)
                return

        for category in selectable_categories:
            category_id = self._category_id(category)
            category_name = self._category_name(category)
            if (
                extracted_id and extracted_id == category_id.lower()
            ) or (
                extracted_name and extracted_name == category_name.lower()
            ):
                job_data["category_id"] = category_id
                job_data["category_name"] = category_name
                return

        # Conservative fallback: choose first category name mentioned in extracted job text.
        haystack = " ".join(str(job_data.get(key, "")) for key in (
            "job_title",
            "job_description",
            "key_responsibilities",
            "qualifications_and_skills",
            "required_experience",
            "educational_level",
            "certification_level",
        )).lower()
        for category in selectable_categories:
            category_name = self._category_name(category)
            if category_name and category_name.lower() in haystack:
                job_data["category_id"] = self._category_id(category)
                job_data["category_name"] = category_name
                return

        other_category = self._other_category(selectable_categories)
        if other_category:
            job_data["category_id"] = self._category_id(other_category)
            job_data["category_name"] = self._category_name(other_category)
            return

        job_data["category_id"] = ""
        job_data["category_name"] = ""

    def _normalize_job_record_for_category_detection(self, job_record: Dict) -> Dict:
        return {
            "job_title": job_record.get("job_title") or job_record.get("jobTitle") or "",
            "job_description": job_record.get("job_description") or job_record.get("description") or "",
            "key_responsibilities": job_record.get("key_responsibilities") or job_record.get("keyResponsibilities") or "",
            "qualifications_and_skills": job_record.get("qualifications_and_skills") or job_record.get("qualifications") or "",
            "educational_level": job_record.get("educational_level") or job_record.get("educationLevel") or "",
            "certification_level": job_record.get("certification_level") or job_record.get("certificationLevel") or "",
            "required_experience": job_record.get("required_experience") or job_record.get("requiredExperience") or "",
        }

    async def detect_child_category_for_job(self, job_record: Dict) -> Dict:
        """Detect exactly one child/leaf category for an existing JobPost record."""
        normalized_job = self._normalize_job_record_for_category_detection(job_record)
        category_options = self._format_categories_for_prompt()
        job_text = "\n".join(
            f"{label}: {normalized_job.get(key, '')}"
            for label, key in (
                ("Job title", "job_title"),
                ("Description", "job_description"),
                ("Key responsibilities", "key_responsibilities"),
                ("Qualifications", "qualifications_and_skills"),
                ("Education level", "educational_level"),
                ("Certification level", "certification_level"),
                ("Required experience", "required_experience"),
            )
            if normalized_job.get(key)
        )

        if not self._selectable_categories():
            return {"category_id": "", "category_name": ""}

        prompt = f"""
        Choose exactly one child/leaf category for this job. Return only valid JSON with:
        - category_id
        - category_name

        Child/leaf category list. Choose only from this list. Do not choose parent categories:
        {category_options}

        Job content:
        {job_text}

        Return the single best matching child/leaf category. If the job is only test/dummy/sample content, return the child category named Test when it exists; otherwise return Other. If no child category matches this job, return the child category named Other. Do not invent a category.
        """

        try:
            response = await self.openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
                messages=[
                    {
                        "role": "system",
                        "content": "You classify jobs into exactly one provided child category and return valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0.1,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            detected = json.loads(content)
        except Exception as e:
            logger.warning(f"AI category detection failed; using deterministic fallback: {e}")
            detected = {}
        if not isinstance(detected, dict):
            detected = {}

        category_data = {
            **normalized_job,
            "category_id": str(detected.get("category_id") or ""),
            "category_name": str(detected.get("category_name") or detected.get("category") or ""),
        }
        self._normalize_extracted_category(category_data)
        return {
            "category_id": category_data.get("category_id", ""),
            "category_name": category_data.get("category_name", ""),
        }

    def _apply_selenium_driver_timeouts(self, driver) -> None:
        """Apply timeouts so navigation/scripts don't hang forever; extend chromedriver HTTP timeout."""
        try:
            driver.set_page_load_timeout(self._selenium_page_load_timeout_seconds())
        except Exception:
            pass
        try:
            driver.set_script_timeout(self._selenium_script_timeout_seconds())
        except Exception:
            pass
        try:
            driver.implicitly_wait(0)
        except Exception:
            pass
        # Selenium 4 ChromiumRemoteConnection defaults to timeout=120; huge DOM page_source can exceed that.
        try:
            executor = getattr(driver, "command_executor", None)
            cc = getattr(executor, "_client_config", None) if executor else None
            if cc is not None:
                cc.timeout = self._selenium_http_timeout_seconds()
                print(f"📡 Selenium chromedriver HTTP timeout set to {cc.timeout}s")
        except Exception as e:
            print(f"⚠️ Could not extend chromedriver HTTP timeout: {e}")

    def _selenium_navigate(self, driver, url: str) -> None:
        """Load URL; on slow pages stop loading and continue with partial DOM."""
        try:
            driver.get(url)
        except TimeoutException:
            print("⚠️ Page load exceeded timeout; stopping resource load and continuing with current DOM")
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

    def _selenium_quit_safe(self, driver) -> None:
        if not driver:
            return
        try:
            driver.quit()
        except Exception as e:
            print(f"⚠️ driver.quit() (ignored): {e}")

    def _accept_cookie_banner_if_present(self, driver) -> None:
        """Click common cookie accept controls before capturing rendered detail HTML."""
        try:
            clicked = driver.execute_script(
                """
                const selectors = [
                    '#CookiePolicyBarButton',
                    'button[id*="CookiePolicyBarButton" i]',
                    'button[id*="cookie"][id*="accept" i]',
                    'button[class*="cookie"][class*="accept" i]',
                    'button[aria-label*="accept" i]',
                    'a[id*="cookie"][id*="accept" i]',
                    'a[class*="cookie"][class*="accept" i]'
                ];
                function visible(el) {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && Number(style.opacity || 1) > 0
                        && rect.width > 0
                        && rect.height > 0;
                }
                for (const selector of selectors) {
                    for (const el of document.querySelectorAll(selector)) {
                        const text = (el.textContent || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
                        if (visible(el) && /accept|continue|agree|allow/.test(text)) {
                            el.click();
                            return true;
                        }
                    }
                }
                for (const el of document.querySelectorAll('button, a, input[type="button"], input[type="submit"]')) {
                    const text = (el.textContent || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (visible(el) && /^(accept(\\s*&\\s*continue)?|accept and continue|agree|allow all|ok)$/i.test(text)) {
                        el.click();
                        return true;
                    }
                }
                return false;
                """
            )
            if clicked:
                print("🍪 Accepted cookie banner")
                time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Cookie accept click skipped: {e}")
    
    def _setup_selenium_driver(self):
        """Setup Chrome WebDriver with proper options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in background
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        # Don't wait for every subresource (analytics, fonts); DOM ready is enough for scraping
        try:
            chrome_options.page_load_strategy = "eager"
        except Exception:
            pass
        # Faster loads for listing pages
        try:
            chrome_options.add_experimental_option(
                "prefs",
                {"profile.managed_default_content_settings.images": 2},
            )
        except Exception:
            pass
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        self._apply_selenium_driver_timeouts(driver)
        return driver
    
    def _get_page_html_with_selenium(self, url: str, wait_for_elements: List[str] = None, delay: int = 2) -> str:
        """Get HTML from page using Selenium with JS/lazy-load stabilization."""
        driver = None
        try:
            print(f"Loading page with Selenium: {url}")
            driver = self._setup_selenium_driver()
            self._selenium_navigate(driver, url)
            
            # Wait for page to load
            print(f"Waiting {delay} seconds for JavaScript to render...")
            time.sleep(delay)
            
            # If specific elements are provided, wait for ANY of them (faster than waiting each one)
            if wait_for_elements:
                combined_selector = ", ".join(wait_for_elements)
                try:
                    # One short wait for any matching selector
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, combined_selector))
                    )
                    print(f"✅ Found page-ready element(s): {combined_selector}")
                except TimeoutException:
                    print("⚠️ Quick wait timeout for job selectors, continue with current DOM")

            # Scroll progressively and wait until the page stabilizes.
            # This helps capture JS-rendered and lazy-loaded job cards.
            print("Scrolling progressively to load JS/lazy job cards...")
            previous_height = driver.execute_script("return document.body.scrollHeight")
            stable_rounds = 0
            max_rounds = 6

            for round_index in range(max_rounds):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.0)

                current_height = driver.execute_script("return document.body.scrollHeight")
                print(
                    f"📜 Scroll round {round_index + 1}/{max_rounds} "
                    f"(height {previous_height} -> {current_height})"
                )

                if current_height == previous_height:
                    stable_rounds += 1
                else:
                    stable_rounds = 0

                previous_height = current_height
                if stable_rounds >= 2:
                    print("✅ Page height stabilized; stop scrolling")
                    break

            # Return to top to avoid edge cases before reading final DOM
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            
            # Get the final HTML
            html = driver.page_source
            print(f"✅ Retrieved HTML: {len(html)} characters")
            
            return html
            
        except Exception as e:
            print(f"❌ Selenium error: {str(e)}")
            return ""
        finally:
            self._selenium_quit_safe(driver)

    def _selenium_collect_careers_jobs_detail_hrefs(self, driver) -> List[str]:
        """
        Collect live anchor hrefs matching .../Careers/jobs/{numeric_id}... (SilkRoad-style).
        Uses the browser DOM (resolves relative URLs); works inside iframes when driver context is set.
        Also scans raw HTML for absolute URLs (some SPAs put links only in templates/scripts).
        """
        try:
            hrefs = driver.execute_script(
                r"""
                var pathRe = /\/careers\/jobs\/\d+/i;
                var absRe = /https?:\/\/[^\s"'<>\\]+(?:\/[A-Za-z0-9_.~-]+)*\/[Cc]areers\/jobs\/\d+[^\s"'<>\\]*/gi;
                var seen = new Set();
                var out = [];
                function add(u) {
                    if (!u || !pathRe.test(u) || seen.has(u)) return;
                    seen.add(u);
                    out.push(u);
                }
                document.querySelectorAll('a[href], area[href]').forEach(function (a) {
                    try { add(a.href); } catch (e) {}
                });
                try {
                    var html = document.documentElement ? document.documentElement.innerHTML : '';
                    var m;
                    absRe.lastIndex = 0;
                    while ((m = absRe.exec(html)) !== null) {
                        add(m[0].replace(/&amp;/g, '&'));
                    }
                } catch (e) {}
                return out;
                """
            )
            return list(hrefs) if hrefs else []
        except Exception as e:
            print(f"⚠️ Careers/jobs DOM href collection failed: {e}")
            return []

    def _silkroad_jobs_domain_from_page(self, driver) -> str:
        """Read data-domain from SilkRoad embed script (jobs-ca vs jobs-us, etc.)."""
        try:
            els = driver.find_elements(By.CSS_SELECTOR, "script#silkroad-cx-snippet, script[data-action='cxEmbedded']")
            for el in els:
                d = (el.get_attribute("data-domain") or "").strip().rstrip("/")
                if d and "silkroad.com" in d.lower():
                    return d
        except Exception:
            pass
        return "https://jobs-ca.silkroad.com"

    def _resolve_silkroad_careers_listing_url(self, landing_url: str, driver) -> Optional[str]:
        """
        Build the real SilkRoad careers listing URL. The iframe often starts as loading.html;
        the parent encodes the target in cxembeddedroot or the snippet provides customer/portal.
        """
        domain = self._silkroad_jobs_domain_from_page(driver)
        try:
            q = parse_qs(urlsplit(landing_url).query)
            raw = (q.get("cxembeddedroot") or [""])[0]
            if raw:
                path_and_query = unquote(raw)
                if not path_and_query.startswith("/"):
                    path_and_query = "/" + path_and_query
                if "embedded=true" not in path_and_query.lower():
                    path_and_query += "&embedded=true" if "?" in path_and_query else "?embedded=true"
                return domain + path_and_query.split("#")[0]
        except Exception:
            pass
        try:
            els = driver.find_elements(By.CSS_SELECTOR, "script#silkroad-cx-snippet, script[data-customercode]")
            for el in els:
                code = (el.get_attribute("data-customercode") or "").strip()
                portal = (el.get_attribute("data-portalcode") or "").strip()
                if code and portal:
                    return f"{domain}/{code}/{portal}?embedded=true"
        except Exception:
            pass
        return None

    def _wait_silkroad_iframe_navigated_from_loading(
        self, driver, timeout: float = 90.0, poll: float = 0.5
    ) -> bool:
        """Wait until #silkroadJobs_cx_container (or silkroad iframe) src is not loading.html."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                driver.switch_to.default_content()
                for sel in ("iframe#silkroadJobs_cx_container", "iframe[src*='silkroad.com']"):
                    for iframe in driver.find_elements(By.CSS_SELECTOR, sel):
                        src = (iframe.get_attribute("src") or "").strip()
                        if not src or "silkroad.com" not in src.lower():
                            continue
                        if "loading.html" in src.lower():
                            continue
                        if len(src) > 40:
                            print(f"✅ SilkRoad iframe navigated: {src[:100]}...")
                            return True
            except Exception:
                pass
            time.sleep(poll)
        return False

    def _force_silkroad_iframe_src(self, driver, listing_url: str) -> bool:
        """Set iframe#silkroadJobs_cx_container src so the real careers app loads (escapes loading.html)."""
        try:
            driver.switch_to.default_content()
            ok = driver.execute_script(
                """
                var u = arguments[0];
                var el = document.getElementById('silkroadJobs_cx_container')
                    || document.querySelector('iframe[src*="silkroad.com"]');
                if (!el || !u) return false;
                el.src = u;
                return true;
                """,
                listing_url,
            )
            if ok:
                print(f"🔧 Forced SilkRoad iframe src to listing: {listing_url[:120]}...")
            return bool(ok)
        except Exception as e:
            print(f"⚠️ Could not force SilkRoad iframe src: {e}")
            return False

    def _selenium_paginate_and_collect_careers_jobs(
        self,
        driver,
        careers_seen: set,
        careers_job_hrefs: List[str],
        max_pages: int = 30,
        max_job_links: Optional[int] = None,
    ) -> None:
        """Click through listing 'Next' pages (SilkRoad-style) and merge /Careers/jobs/{id} hrefs."""
        next_selectors = [
            "a[rel='next']",
            "a[aria-label*='Next' i]",
            "a[aria-label*='next page' i]",
            "li.next:not(.disabled) a",
            "li.pager-next a",
            ".pagination a.next",
            "a.pager-next",
            "a#lnkPagerNext",
        ]
        for _ in range(max_pages):
            if max_job_links is not None and len(careers_job_hrefs) >= max_job_links:
                break
            clicked = False
            for sel in next_selectors:
                try:
                    for el in driver.find_elements(By.CSS_SELECTOR, sel):
                        try:
                            if not el.is_displayed():
                                continue
                            driver.execute_script("arguments[0].click();", el)
                            clicked = True
                            time.sleep(2.0)
                            for h in self._selenium_collect_careers_jobs_detail_hrefs(driver):
                                if h not in careers_seen:
                                    careers_seen.add(h)
                                    careers_job_hrefs.append(h)
                                    if max_job_links is not None and len(careers_job_hrefs) >= max_job_links:
                                        break
                            break
                        except Exception:
                            continue
                    if clicked:
                        break
                except Exception:
                    continue
            if not clicked:
                break

    def _get_listing_html_chunks(
        self,
        url: str,
        wait_for_elements: Optional[List[str]] = None,
        delay: int = 2,
        iframe_scroll_rounds: int = 14,
        max_job_links: Optional[int] = None,
    ) -> Tuple[List[Tuple[str, str]], List[str]]:
        """
        Load landing page once, return:
        - [(base_url, html), ...] for the main document and each iframe's *live* inner HTML.
        - merged list of SilkRoad-style detail URLs (.../Careers/jobs/{id}) seen in the DOM
          while scrolling (main + every iframe), so virtualized lists are captured incrementally.
        """
        driver = None
        chunks: List[Tuple[str, str]] = []
        careers_job_hrefs: List[str] = []
        careers_seen = set()

        def enough_job_links() -> bool:
            return max_job_links is not None and len(careers_job_hrefs) >= max_job_links

        def collect_new_careers_links() -> int:
            added = 0
            for h in self._selenium_collect_careers_jobs_detail_hrefs(driver):
                if h not in careers_seen:
                    careers_seen.add(h)
                    careers_job_hrefs.append(h)
                    added += 1
                    if enough_job_links():
                        break
            return added

        def wait_for_scroll_update(height_script: str, previous_height: int, timeout: float, poll: float = 0.1) -> int:
            """Poll briefly after scrolling; return as soon as links or height change."""
            deadline = time.time() + timeout
            current_height = previous_height
            while time.time() < deadline:
                if collect_new_careers_links() > 0 or enough_job_links():
                    break
                try:
                    current_height = driver.execute_script(height_script)
                    if current_height != previous_height:
                        break
                except Exception:
                    break
                time.sleep(poll)
            return current_height

        try:
            print(f"Loading listing page + iframes (single session): {url}")
            driver = self._setup_selenium_driver()
            self._selenium_navigate(driver, url)

            print(f"Waiting {delay} seconds for JavaScript to render...")
            time.sleep(delay)

            if wait_for_elements:
                combined_selector = ", ".join(wait_for_elements)
                selector_wait_timeout = 4 if self.fast_mode else 8
                try:
                    WebDriverWait(driver, selector_wait_timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, combined_selector))
                    )
                    print(f"✅ Found page-ready element(s): {combined_selector}")
                except TimeoutException:
                    print("⚠️ Quick wait timeout for job selectors, continue with current DOM")

            collect_new_careers_links()
            if self._skip_main_document_scroll():
                print("⏭️ Skipping main-document progressive scroll in fast mode")
            else:
                print("Scrolling progressively to load JS/lazy job cards (main document)...")
                main_height_script = "return document.body.scrollHeight"
                previous_height = driver.execute_script(main_height_script)
                stable_rounds = 0
                max_rounds = 4 if self.fast_mode else 6
                main_scroll_timeout = 0.8 if self.fast_mode else 1.2
                for round_index in range(max_rounds):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    current_height = wait_for_scroll_update(
                        main_height_script,
                        previous_height,
                        main_scroll_timeout,
                    )
                    if enough_job_links():
                        break
                    if current_height == previous_height:
                        stable_rounds += 1
                    else:
                        stable_rounds = 0
                    previous_height = current_height
                    if stable_rounds >= 2:
                        break
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.1 if self.fast_mode else 0.5)
            collect_new_careers_links()

            # SilkRoad embed: iframe starts as loading.html; snippet swaps src async — often still
            # loading when we snapshot. Resolve real listing URL from cxembeddedroot / data-* and set src.
            driver.switch_to.default_content()
            resolved_listing = self._resolve_silkroad_careers_listing_url(url, driver)
            if resolved_listing:
                print(f"📎 Resolved SilkRoad listing URL: {resolved_listing[:140]}...")
                first_iframe_wait = 8.0 if self.fast_mode else 25.0
                second_iframe_wait = 20.0 if self.fast_mode else 90.0
                iframe_settle_sleep = 1.5 if self.fast_mode else 4.0
                if not self._wait_silkroad_iframe_navigated_from_loading(driver, timeout=first_iframe_wait):
                    self._force_silkroad_iframe_src(driver, resolved_listing)
                    time.sleep(0.5 if self.fast_mode else 2)
                self._wait_silkroad_iframe_navigated_from_loading(driver, timeout=second_iframe_wait)
                time.sleep(iframe_settle_sleep)
            else:
                self._wait_silkroad_iframe_navigated_from_loading(driver, timeout=5.0 if self.fast_mode else 60.0)

            main_html = driver.page_source
            chunks.append((url, main_html))
            print(f"✅ Main document HTML: {len(main_html)} characters")

            driver.switch_to.default_content()
            iframe_wait_selector = (
                "a[href*='/Careers/jobs/'], a[href*='/careers/jobs/'], "
                "a[href*='/jobs/'], a[href*='/job/'], a[href*='Careers'], "
                "a[href*='careers'], a[href*='Job'], [data-job-id], [data-testid*='job']"
            )

            def _ordered_iframes_for_jobs(driver_):
                """SilkRoad job embed first; skip obvious tracking iframes."""
                frames = driver_.find_elements(By.TAG_NAME, "iframe")
                sil = [
                    f for f in frames
                    if (f.get_attribute("id") or "") == "silkroadJobs_cx_container"
                ]
                rest = [
                    f for f in frames
                    if (f.get_attribute("id") or "") != "silkroadJobs_cx_container"
                    and "googletagmanager" not in ((f.get_attribute("src") or "").lower())
                    and "doubleclick.net" not in ((f.get_attribute("src") or "").lower())
                ]
                return sil + rest

            top_iframes = _ordered_iframes_for_jobs(driver)
            print(f"🧩 Found {len(driver.find_elements(By.TAG_NAME, 'iframe'))} iframe(s); "
                  f"processing {len(top_iframes)} (prioritize SilkRoad, skip trackers)")

            for idx in range(len(top_iframes)):
                if enough_job_links():
                    break
                driver.switch_to.default_content()
                iframes_now = _ordered_iframes_for_jobs(driver)
                if idx >= len(iframes_now):
                    break
                el = iframes_now[idx]
                src = (el.get_attribute("src") or "").strip()
                iframe_base = urljoin(url, src) if src else url
                # If still on loading.html, force real listing URL once more
                if resolved_listing and "loading.html" in src.lower():
                    self._force_silkroad_iframe_src(driver, resolved_listing)
                    time.sleep(1.5 if self.fast_mode else 4)
                    driver.switch_to.default_content()
                    el = driver.find_elements(By.ID, "silkroadJobs_cx_container")
                    el = el[0] if el else iframes_now[idx]
                    src = (el.get_attribute("src") or "").strip()
                    iframe_base = urljoin(url, src) if src else url
                try:
                    driver.switch_to.frame(el)
                    time.sleep(max(1.0, delay) if self.fast_mode else max(2, delay))
                    try:
                        WebDriverWait(driver, 6 if self.fast_mode else 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, iframe_wait_selector))
                        )
                        print(f"✅ Iframe {idx} ready ({iframe_base[:80]}...)")
                    except TimeoutException:
                        print(f"⚠️ Iframe {idx}: no job-like links quickly; still capturing DOM")

                    # Scroll iframe and collect /Careers/jobs/{id} hrefs each step (virtualized lists)
                    stable = 0
                    iframe_height_script = (
                        "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
                    )
                    prev = driver.execute_script(iframe_height_script)
                    iframe_rounds = min(iframe_scroll_rounds, 6) if self.fast_mode else iframe_scroll_rounds
                    iframe_scroll_timeout = 0.6 if self.fast_mode else 0.8
                    for r in range(iframe_rounds):
                        driver.execute_script(
                            "window.scrollTo(0, Math.max(document.body.scrollHeight, "
                            "document.documentElement.scrollHeight));"
                        )
                        cur = wait_for_scroll_update(
                            iframe_height_script,
                            prev,
                            iframe_scroll_timeout,
                        )
                        if enough_job_links():
                            break
                        if cur == prev:
                            stable += 1
                            if stable >= 2 and r > 1:
                                break
                        else:
                            stable = 0
                        prev = cur
                    collect_new_careers_links()

                    if "silkroad" in iframe_base.lower() and not enough_job_links():
                        print(f"📄 SilkRoad iframe: paginating to collect all /Careers/jobs/{{id}} links...")
                        self._selenium_paginate_and_collect_careers_jobs(
                            driver, careers_seen, careers_job_hrefs, max_job_links=max_job_links
                        )

                    inner_html = driver.page_source
                    chunks.append((iframe_base, inner_html))
                    print(f"✅ Iframe {idx} inner HTML: {len(inner_html)} characters")

                    # One level of nested iframes (some ATS embed twice)
                    nested = driver.find_elements(By.TAG_NAME, "iframe")
                    for j in range(len(nested)):
                        if enough_job_links():
                            break
                        try:
                            in_list = driver.find_elements(By.TAG_NAME, "iframe")
                            if j >= len(in_list):
                                break
                            nel = in_list[j]
                            nsrc = (nel.get_attribute("src") or "").strip()
                            nbase = urljoin(iframe_base, nsrc) if nsrc else iframe_base
                            driver.switch_to.frame(nel)
                            time.sleep(0.75 if self.fast_mode else 2)
                            try:
                                WebDriverWait(driver, 4 if self.fast_mode else 12).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, iframe_wait_selector))
                                )
                            except TimeoutException:
                                pass
                            stable_n = 0
                            nested_height_script = (
                                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
                            )
                            prev_n = driver.execute_script(nested_height_script)
                            nested_rounds = 4 if self.fast_mode else 8
                            nested_timeout = 0.5 if self.fast_mode else 0.75
                            for r in range(nested_rounds):
                                driver.execute_script(
                                    "window.scrollTo(0, Math.max(document.body.scrollHeight, "
                                    "document.documentElement.scrollHeight));"
                                )
                                cur_n = wait_for_scroll_update(
                                    nested_height_script,
                                    prev_n,
                                    nested_timeout,
                                )
                                if enough_job_links():
                                    break
                                if cur_n == prev_n:
                                    stable_n += 1
                                    if stable_n >= 2 and r > 1:
                                        break
                                else:
                                    stable_n = 0
                                prev_n = cur_n
                            collect_new_careers_links()

                            if "silkroad" in nbase.lower() and not enough_job_links():
                                print(f"📄 Nested SilkRoad iframe: paginating...")
                                self._selenium_paginate_and_collect_careers_jobs(
                                    driver, careers_seen, careers_job_hrefs, max_job_links=max_job_links
                                )

                            chunks.append((nbase, driver.page_source))
                            print(f"✅ Nested iframe {idx}/{j} HTML: {len(driver.page_source)} chars")
                        except Exception as nest_err:
                            print(f"⚠️ Nested iframe {idx}/{j} skipped: {nest_err}")
                        finally:
                            try:
                                driver.switch_to.parent_frame()
                            except Exception:
                                driver.switch_to.default_content()
                                driver.switch_to.frame(el)
                except Exception as frame_err:
                    print(f"⚠️ Top iframe {idx} failed: {frame_err}")
                finally:
                    driver.switch_to.default_content()

            print(
                f"🔗 Collected {len(careers_job_hrefs)} unique /Careers/jobs/{{id}} URLs from live DOM "
                f"(main + iframes)"
            )
            return chunks, careers_job_hrefs
        except Exception as e:
            print(f"❌ Selenium error (listing chunks): {str(e)}")
            return (chunks if chunks else [], careers_job_hrefs)
        finally:
            self._selenium_quit_safe(driver)

    def _extract_detail_job_urls_regex(self, html: str, base_url: str) -> List[str]:
        """Find absolute detail URLs in raw HTML (scripts, JSON, data-attrs), e.g. SilkRoad /Careers/jobs/123."""
        if not html:
            return []
        out: List[str] = []
        seen = set()

        # Absolute URLs containing /jobs/<digits>
        for m in re.finditer(
            r"https?://[^\s\"'<>]+?(?:/[Cc]areers)?/jobs/\d+[^\s\"'<>]*",
            html,
            re.IGNORECASE,
        ):
            u = m.group(0).rstrip(",.;)]}>\"'")
            if u not in seen:
                seen.add(u)
                out.append(u)

        # Quoted relative or absolute in href / data attributes
        for m in re.finditer(
            r'(?:href|data-href|data-url|data-link)\s*=\s*["\']([^"\']*(?:/[Cc]areers)?/jobs/\d+[^"\']*)["\']',
            html,
            re.IGNORECASE,
        ):
            u = urljoin(base_url, m.group(1).strip())
            if u not in seen:
                seen.add(u)
                out.append(u)

        # Full absolute URLs with one-or-more path segments before /Careers/jobs/{id}
        # e.g. https://jobs-ca.silkroad.com/Brandt/Careers/jobs/11381?embedded=true
        for m in re.finditer(
            r'https?://[^\s"\'<>\\]+(?:/[A-Za-z0-9_.~-]+)*/[Cc]areers/jobs/\d+[^\s"\'<>\\]*',
            html,
            re.IGNORECASE,
        ):
            u = m.group(0).rstrip(",.;)]}>\"'")
            if u not in seen:
                seen.add(u)
                out.append(u)

        # JSON-escaped full URLs (e.g. "https:\\/\\/jobs-ca.silkroad.com\\/Brandt\\/Careers\\/jobs\\/11381")
        for m in re.finditer(
            r'https?:\\?/\\?/[^\s"\'<>\\]+(?:\\?/\\?[A-Za-z0-9_.~-]+)*\\?/\\?[Cc]areers\\?/\\?jobs\\?/\\?\d+[^\s"\'<>\\]*',
            html,
        ):
            u = (
                m.group(0)
                .replace("\\/", "/")
                .replace("\\\\", "\\")
                .rstrip(",.;)]}>\"'")
            )
            if u not in seen:
                seen.add(u)
                out.append(u)

        # OpportunityDetail / JobBoard URLs with opportunityId GUID
        for m in re.finditer(
            r'https?://[^\s"\'<>]+/JobBoard/[^\s"\'<>]*OpportunityDetail[^\s"\'<>]*opportunityId=[0-9a-fA-F-]+',
            html,
            re.IGNORECASE,
        ):
            u = m.group(0).rstrip(",.;)]}>\"'")
            if u not in seen:
                seen.add(u)
                out.append(u)

        # Quoted href variants for OpportunityDetail
        for m in re.finditer(
            r'(?:href|data-href|data-url)\s*=\s*["\']([^"\']*OpportunityDetail[^"\']*opportunityId=[0-9a-fA-F-]+[^"\']*)["\']',
            html,
            re.IGNORECASE,
        ):
            u = urljoin(base_url, m.group(1).strip())
            if u not in seen:
                seen.add(u)
                out.append(u)

        return out

    def _normalize_url_remove_query(self, url: str) -> str:
        """Normalize URL for dedupe by removing query/fragment.
        
        For OpportunityDetail URLs the job identity lives in the opportunityId
        query param, so we keep that param to avoid collapsing distinct jobs.
        """
        try:
            parts = urlsplit(url)
            if "OpportunityDetail" in parts.path:
                qs = parse_qs(parts.query)
                opp_id = qs.get("opportunityId", [None])[0]
                if opp_id:
                    return urlunsplit((parts.scheme, parts.netloc, parts.path, f"opportunityId={opp_id}", ""))
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        except Exception:
            # Best-effort fallback
            return url.split("?", 1)[0].split("#", 1)[0]
    
    def _is_url_scraped(self, url: str) -> bool:
        """Check if a URL has already been scraped"""
        normalized = self._normalize_url_remove_query(url)
        return normalized in self.scraped_urls
    
    def _mark_url_scraped(self, url: str):
        """Mark a URL as scraped"""
        normalized = self._normalize_url_remove_query(url)
        self.scraped_urls.add(normalized)

    def _normalize_existing_source_urls(self, existing_source_urls: set) -> set:
        """Normalize DB source URLs for duplicate checks before detail scraping."""
        return {
            self._normalize_url_remove_query(existing_url)
            for existing_url in existing_source_urls
            if existing_url
        }

    async def _load_existing_source_urls_from_db(self) -> set:
        """Load existing JobPost sourceUrl values when caller did not provide them."""
        db = None
        try:
            from database import Database

            db = Database()
            await db.connect()
            source_urls = await db.get_scraped_source_urls()
            print(f"🔎 Loaded {len(source_urls)} existing JobPost source URLs from DB")
            return source_urls
        except Exception as e:
            print(f"⚠️ Could not load existing JobPost source URLs from DB; duplicate DB skip disabled: {e}")
            return set()
        finally:
            if db:
                await db.close()
    
    def _add_scraped_job(self, job_data: Dict):
        """Add a successfully scraped job to the list"""
        self.scraped_jobs.append(job_data)
    
    def get_scraped_jobs(self) -> List[Dict]:
        """Get all successfully scraped jobs"""
        return self.scraped_jobs
    
    def get_scraped_urls(self) -> set:
        """Get all scraped URLs"""
        return self.scraped_urls.copy()
    
    def reset_scraping_state(self):
        """Reset the scraping state for a new scraping session"""
        self.scraped_urls.clear()
        self.scraped_jobs.clear()
    
    def save_scraping_state(self, filename: str = "scraping_state.json"):
        """Save the current scraping state to a file"""
        try:
            state = {
                "scraped_urls": list(self.scraped_urls),
                "scraped_jobs": self.scraped_jobs,
                "timestamp": datetime.now().isoformat()
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Saved scraping state to {filename}")
            return True
        except Exception as e:
            print(f"❌ Failed to save scraping state: {str(e)}")
            return False
    
    def load_scraping_state(self, filename: str = "scraping_state.json"):
        """Load the scraping state from a file"""
        try:
            if not os.path.exists(filename):
                print(f"📄 No existing scraping state file found: {filename}")
                return False
            
            with open(filename, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            self.scraped_urls = set(state.get("scraped_urls", []))
            self.scraped_jobs = state.get("scraped_jobs", [])
            
            print(f"📂 Loaded scraping state from {filename}")
            print(f"   - {len(self.scraped_urls)} scraped URLs")
            print(f"   - {len(self.scraped_jobs)} scraped jobs")
            return True
        except Exception as e:
            print(f"❌ Failed to load scraping state: {str(e)}")
            return False
    
    def _save_html_debug(self, html_content: str, url: str, page_type: str = "page"):
        """Save HTML content to a debug file for inspection"""
        if not self.save_debug_html:
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Clean URL for filename
            url_clean = re.sub(r'[^\w\-_\.]', '_', url.replace('https://', '').replace('http://', ''))
            filename = f"{page_type}_{url_clean}_{timestamp}.html"
            filepath = os.path.join(self.debug_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"💾 Saved HTML debug file: {filepath}")
            return filepath
        except Exception as e:
            print(f"❌ Failed to save HTML debug file: {str(e)}")
            return None
        
    async def scrape_jobs(
        self,
        url: str,
        max_jobs: Optional[int] = None,
        existing_source_urls: Optional[set] = None,
    ) -> List[Dict]:
        """Main function to scrape all jobs from a given URL with pagination support.
        If max_jobs is set, scraping stops after that many jobs have been successfully scraped."""
        # Reset scraping state for new session
        self.reset_scraping_state()
        if existing_source_urls is None:
            existing_source_urls = await self._load_existing_source_urls_from_db()
        existing_normalized_urls = self._normalize_existing_source_urls(existing_source_urls)
        
        try:
            # Get the initial page HTML using Selenium
            print(f"Scraping URL with Selenium: {url}")
            if max_jobs is not None:
                print(f"📌 Max jobs limit: {max_jobs}")

            landing_url_normalized = self._normalize_url_remove_query(url)
            
            # Wait for job elements to appear
            wait_for_elements = [
                "iframe",
                "a[href*='/Careers/jobs/']",
                "a[href*='/careers/jobs/']",
                ".jobCardTitle",
                "[data-testid^='jobCardTitle_']",
                ".JobsList_jobCardTitle__pRNjw",
                "a[href*='/job/']",
            ]
            
            # Single Selenium session: main + iframe HTML + live /Careers/jobs/{id} href collection.
            # For small API requests, collect a small buffer instead of exhausting large listings.
            max_job_links = None if max_jobs is None else max(max_jobs * 6, max_jobs + 12)
            html_chunks, dom_careers_job_urls = self._get_listing_html_chunks(
                url,
                wait_for_elements,
                delay=1.5 if self.fast_mode else 2,
                iframe_scroll_rounds=6 if self.fast_mode else 14,
                max_job_links=max_job_links,
            )
            if not html_chunks:
                raise Exception(f"Failed to get HTML from URL: {url}")

            # Mark main page URL as scraped
            self._mark_url_scraped(url)

            # Save the main page HTML for debugging (first chunk = parent document)
            self._save_html_debug(html_chunks[0][1], url, "main_listing")

            job_links: List[str] = []
            job_links.extend(dom_careers_job_urls)
            print(f"✅ DOM-collected SilkRoad-style /Careers/jobs/{{id}} URLs: {len(dom_careers_job_urls)}")
            for chunk_base, chunk_html in html_chunks:
                if max_job_links is not None and len(set(job_links)) >= max_job_links:
                    break
                chunk_links = await self._extract_job_links(
                    chunk_html,
                    chunk_base,
                    max_links=max_job_links,
                )
                job_links.extend(chunk_links)
                print(f"✅ Extracted {len(chunk_links)} links from chunk base {chunk_base[:90]}...")
            print(f"✅ Total raw job links (DOM + all HTML chunks): {len(job_links)}")
            
            if not job_links:
                print("❌ No job links found")
                return []
            
            # Remove duplicates by URL without query/fragment, and ignore landing page URL
            unique_by_normalized: Dict[str, str] = {}
            ignored_landing = 0
            for link in job_links:
                normalized = self._normalize_url_remove_query(link)
                if normalized == landing_url_normalized:
                    ignored_landing += 1
                    continue
                unique_by_normalized.setdefault(normalized, link)

            unique_job_links = list(unique_by_normalized.values())
            print(
                f"📋 Processing {len(unique_job_links)} unique job links "
                f"(ignored {ignored_landing} landing-page links; deduped by URL without query)"
            )
            
            # Scrape individual job details using Crawl4AI for AI extraction

            all_jobs = []
            async with AsyncWebCrawler(verbose=False) as crawler:
                for i, job_url in enumerate(unique_job_links, 1):
                    # Stop when we have enough jobs
                    if max_jobs is not None and len(all_jobs) >= max_jobs:
                        print(f"🛑 Reached max_jobs limit ({max_jobs}), stopping")
                        break
                    try:
                        # Check if URL has already been scraped
                        if self._is_url_scraped(job_url):
                            print(f"⏭️ Skipping already scraped job {i}/{len(unique_job_links)}: {job_url}")
                            continue

                        normalized_job_url = self._normalize_url_remove_query(job_url)
                        if normalized_job_url in existing_normalized_urls:
                            print(f"⏭️ Skipping existing JobPost sourceUrl {i}/{len(unique_job_links)}: {job_url}")
                            self._mark_url_scraped(job_url)
                            continue
                        
                        print(f"🔄 Scraping job {i}/{len(unique_job_links)}: {job_url}")
                        job_data = await self._scrape_individual_job_with_crawl4ai(
                            job_url,
                            crawler=crawler,
                        )
                        
                        if job_data:
                            # If job_title is missing, this likely isn't a detailed job page
                            job_title = (job_data.get("job_title") or "").strip()
                            if not job_title:
                                print(f"⏭️ Skipping non-detail page (missing job_title): {job_url}")
                                continue

                            # Apply location filter if enabled
                            if self.filter_location:
                                location = job_data.get('location', '')
                                if not self._is_canada_or_us_location(location):
                                    print(f"⏭️ Skipping job {i}/{len(unique_job_links)} - location '{location}' is not Canada or US")
                                    continue
                            
                            # Mark URL as scraped and add job data
                            self._mark_url_scraped(job_url)
                            self._add_scraped_job(job_data)
                            all_jobs.append(job_data)
                            print(f"✅ Successfully scraped job {i}/{len(unique_job_links)}")
                        else:
                            print(f"❌ Failed to extract data from job {i}/{len(unique_job_links)}")
                            
                    except Exception as e:
                        print(f"❌ Error scraping job {i}/{len(unique_job_links)} {job_url}: {str(e)}")
                        continue
                
                
            print(f"🎉 Scraping completed! Successfully scraped {len(all_jobs)} jobs")
            return all_jobs
                
        except Exception as e:
            print(f"❌ Error in scrape_jobs: {str(e)}")
            return []
    
    async def _extract_job_links(
        self,
        html: str,
        base_url: str,
        max_links: Optional[int] = None,
    ) -> List[str]:
        """Extract job links from the HTML content, ignoring headers and footers"""
        soup = BeautifulSoup(html, 'html.parser')
        job_links = []

        def has_enough_links() -> bool:
            return max_links is not None and len(set(job_links)) >= max_links
        
        # Only remove head and footer elements - keep everything else
        elements_to_remove = [
            'head', 'footer'
        ]
        
        if not self.fast_mode:
            print(f"Removing only <head> and <footer> elements...")
        removed_count = 0
        for selector in elements_to_remove:
            try:
                elements = soup.select(selector)
                for element in elements:
                    element.decompose()
                    removed_count += 1
            except Exception as e:
                continue
        
        if not self.fast_mode:
            print(f"Removed {removed_count} <head>/<footer> elements")
        
        # Use the entire remaining document (no main content filtering)
        main_content = soup
        if not self.fast_mode:
            print("Using entire document after <head>/<footer> removal")
        
        # Enhanced selectors for job links - prioritizing the exact patterns from the HTML
        job_link_selectors = [
            # Explicit detailed-job patterns (high priority)
            'a[href*="/Careers/jobs/"]',
            'a[href*="/careers/jobs/"]',
            'a[href*="/jobs/"]',
            'a[href*="/job/"][href*="/Careers/"]',
            # OpportunityDetail / JobBoard pattern
            'a[href*="OpportunityDetail"]',
            'a[href*="/JobBoard/"]',
            'a[data-automation="job-title"]',
            'a.opportunity-link',
            # EXACT patterns from the provided HTML
            'a.jobCardTitle.JobsList_jobCardTitle__pRNjw',  # Most specific match
            'a[data-testid^="jobCardTitle_"]',  # Exact data-testid pattern
            '.JobsList_jobCardTitle__pRNjw',   # Exact class from HTML
            'a.jobCardTitle',                  # Generic class
            # Backup patterns
            'a[class*="jobCardTitle"]',
            'a[data-testid*="jobCardTitle"]',
            'a[href^="/job/"]',               # Exact href pattern from HTML
            'a[href*="/job/"]',
            'a[href*="job"]',
            # Less specific fallbacks
            'a[href*="career"]',
            'a[href*="vacancy"]',
            'a[href*="position"]',
            '.job-title a',
            '.job-link',
            '.position-title a',
            '.job-card a',
            '.job-item a',
            '.listing-item a',
            '[data-job-id] a',
            '[data-testid*="job"] a',
            'a[data-testid*="jobCard"]',
            '.job a', '.jobs a', '.listing a', '.position a',
            'a[aria-label*="job" i]',
            'a[title*="job" i]'
        ]
        
        if not self.fast_mode:
            print(f"Extracting job links from cleaned document...")
        
        # DEBUG: Show a sample of the remaining HTML to verify structure
        if not self.fast_mode:
            remaining_html_sample = str(main_content)[:2000]
            print(f"Sample of remaining HTML after cleaning: {remaining_html_sample[:500]}...")
            
            # DEBUG: Check for specific patterns in the HTML
            if 'jobCardTitle' in remaining_html_sample:
                print("✅ Found 'jobCardTitle' in HTML")
            if 'JobsList_jobCardTitle__pRNjw' in remaining_html_sample:
                print("✅ Found 'JobsList_jobCardTitle__pRNjw' class in HTML")
            if 'data-testid="jobCardTitle_' in remaining_html_sample:
                print("✅ Found 'data-testid=\"jobCardTitle_\"' in HTML")
            if '/job/' in remaining_html_sample:
                print("✅ Found '/job/' href pattern in HTML")
        
        for selector in job_link_selectors:
            if has_enough_links():
                break
            try:
                # Search within the cleaned document
                links = main_content.select(selector)
                if not self.fast_mode:
                    print(f"Selector '{selector}' found {len(links)} links")
                
                for link in links:
                    if has_enough_links():
                        break
                    # Check if this link is inside an element with "header" or "footer" in id/class
                    # (even though we removed such elements, check parent chain to be safe)
                    is_in_header_footer = False
                    parent = link.parent
                    while parent:
                        if hasattr(parent, 'get'):
                            parent_id = parent.get('id', '') or ''
                            parent_class = parent.get('class', [])
                            if isinstance(parent_class, list):
                                parent_class = ' '.join(parent_class)
                            else:
                                parent_class = str(parent_class) or ''
                            
                            id_lower = parent_id.lower()
                            class_lower = parent_class.lower()
                            
                            if 'header' in id_lower or 'footer' in id_lower or \
                               'header' in class_lower or 'footer' in class_lower:
                                is_in_header_footer = True
                                break
                        
                        if parent == soup or parent.name == '[document]':
                            break
                        parent = getattr(parent, 'parent', None)
                    
                    if is_in_header_footer:
                        if not self.fast_mode:
                            print(f"Skipping link inside header/footer: {link.get('href', '')}")
                        continue
                    
                    href = link.get('href')
                    if href:
                        full_url = urljoin(base_url, href)
                        # Simplified validation - just check if it's a job URL
                        if self._is_job_url(full_url):
                            job_links.append(full_url)
                            if not self.fast_mode:
                                print(f"Added job link: {full_url}")
            except Exception as e:
                if not self.fast_mode:
                    print(f"Error with selector '{selector}': {str(e)}")
                continue

        # Regex pass: picks up URLs in script/JSON or non-standard attributes (common in SPAs / SilkRoad)
        if not has_enough_links():
            for ru in self._extract_detail_job_urls_regex(html, base_url):
                if re.search(r"/(?:[Cc]areers/)?jobs/\d+", ru) or re.search(r"OpportunityDetail.*opportunityId=", ru, re.IGNORECASE):
                    job_links.append(ru)
                    if not self.fast_mode:
                        print(f"Added job link (regex): {ru}")
                    if has_enough_links():
                        break
        
        unique_links = list(dict.fromkeys(job_links))  # Remove duplicates while preserving listing order
        print(f"Total unique job links found: {len(unique_links)}")
        return unique_links

    def _extract_iframe_src_urls(self, html: str, base_url: str) -> List[str]:
        """Extract iframe src URLs that may contain embedded job listings."""
        iframe_urls: List[str] = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for iframe in soup.find_all('iframe'):
                src = (iframe.get('src') or '').strip()
                if not src:
                    continue
                full_src = urljoin(base_url, src)
                src_lower = full_src.lower()
                if any(keyword in src_lower for keyword in ['career', 'jobs', 'silkroad', 'embedded=true']):
                    iframe_urls.append(full_src)
                    print(f"Found job-related iframe src: {full_src}")
        except Exception as e:
            print(f"⚠️ Failed to parse iframe src URLs: {str(e)}")
            return []

        # Deduplicate while preserving order
        unique_iframe_urls = list(dict.fromkeys(iframe_urls))
        return unique_iframe_urls
    
    def _is_job_url(self, url: str) -> bool:
        """Check if a URL is likely a job posting URL"""
        url_lower = url.lower()

        # Strong detailed-job patterns (e.g. /Careers/jobs/11381)
        detailed_patterns = [
            r'/careers/jobs/\d+',
            r'/jobs/\d+',
            r'/job/\d+',
            r'jobid=\d+',
            r'id=\d+',
            r'OpportunityDetail\?.*opportunityId=[0-9a-fA-F-]+',
            r'/JobBoard/[0-9a-fA-F-]+/OpportunityDetail',
        ]
        for pattern in detailed_patterns:
            if re.search(pattern, url_lower):
                return True

        # Generic fallback
        job_keywords = ['job', 'career', 'vacancy', 'position', 'employment', 'hiring']
        return any(keyword in url_lower for keyword in job_keywords)
    
    def _is_canada_or_us_location(self, location: str) -> bool:
        """Check if a location string contains Canada or US"""
        if not location:
            return False
        
        location_lower = location.lower()
        
        # Check for Canada
        canada_keywords = ['canada', 'canadian', 'ontario', 'british columbia', 'bc', 'alberta', 
                          'quebec', 'manitoba', 'saskatchewan', 'nova scotia', 'new brunswick',
                          'newfoundland', 'pei', 'prince edward island', 'yukon', 'northwest territories',
                          'nunavut', 'toronto', 'vancouver', 'montreal', 'calgary', 'edmonton',
                          'ottawa', 'winnipeg', 'halifax']
        
        # Check for US
        us_keywords = ['united states', 'usa', 'us', 'u.s.', 'u.s.a.', 'america', 'american',
                      'california', 'texas', 'florida', 'new york', 'illinois', 'pennsylvania',
                      'ohio', 'georgia', 'north carolina', 'michigan', 'new jersey', 'virginia',
                      'washington', 'arizona', 'massachusetts', 'tennessee', 'indiana', 'missouri',
                      'maryland', 'wisconsin', 'colorado', 'minnesota', 'south carolina',
                      'alabama', 'louisiana', 'kentucky', 'oregon', 'oklahoma', 'connecticut',
                      'utah', 'iowa', 'nevada', 'arkansas', 'mississippi', 'kansas', 'new mexico',
                      'nebraska', 'west virginia', 'idaho', 'hawaii', 'new hampshire', 'maine',
                      'montana', 'rhode island', 'delaware', 'south dakota', 'north dakota',
                      'alaska', 'vermont', 'wyoming', 'washington dc', 'district of columbia',
                      'los angeles', 'chicago', 'houston', 'phoenix', 'philadelphia', 'san antonio',
                      'san diego', 'dallas', 'san jose', 'austin', 'jacksonville', 'san francisco',
                      'columbus', 'fort worth', 'charlotte', 'detroit', 'el paso', 'seattle',
                      'denver', 'boston', 'nashville', 'oklahoma city', 'portland']
        
        # Check if location contains Canada keywords
        for keyword in canada_keywords:
            if keyword in location_lower:
                return True
        
        # Check if location contains US keywords
        for keyword in us_keywords:
            if keyword in location_lower:
                return True
        
        # Check for US state abbreviations (2 letters)
        import re
        us_state_pattern = r'\b([a-z]{2})\b'
        matches = re.findall(us_state_pattern, location_lower)
        # Common US state abbreviations (excluding common 2-letter words)
        us_states_abbrev = ['al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga',
                           'hi', 'id', 'il', 'in', 'ia', 'ks', 'ky', 'la', 'me', 'md',
                           'ma', 'mi', 'mn', 'ms', 'mo', 'mt', 'ne', 'nv', 'nh', 'nj',
                           'nm', 'ny', 'nc', 'nd', 'oh', 'ok', 'or', 'pa', 'ri', 'sc',
                           'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv', 'wi', 'wy', 'dc']
        if any(match in us_states_abbrev for match in matches):
            return True
        
        return False
    
    def _is_valid_job_link(self, link_element) -> bool:
        """Additional validation to ensure the link is actually a job posting"""
        # Skip links that are likely navigation or utility links
        link_text = link_element.get_text(strip=True).lower()
        href = link_element.get('href', '').lower()
        
        # Skip common navigation/utility links
        skip_patterns = [
            'login', 'register', 'sign in', 'sign up', 'logout',
            'contact', 'about', 'help', 'support', 'faq',
            'home', 'back', 'previous', 'next page', 'page',
            'privacy', 'terms', 'cookie', 'legal',
            'search', 'filter', 'sort', 'view all',
            'company', 'employer', 'recruiter'
        ]
        
        # Skip if link text matches navigation patterns
        for pattern in skip_patterns:
            if pattern in link_text or pattern in href:
                return False
        
        # Skip very short link texts that are likely not job titles
        if len(link_text) < 3:
            return False
        
        # Skip links that don't have meaningful text
        if not link_text or link_text in ['', ' ', 'click here', 'read more', 'apply', 'view']:
            return False
        
        return True
    
    async def _handle_pagination(self, base_url: str, html: str) -> List[str]:
        """Handle pagination to get all job links from all pages"""
        all_job_links = []
        
        # Look for pagination elements
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove head, header, and footer tags for pagination detection
        for head in soup.find_all('head'):
            head.decompose()
        for header in soup.find_all('header'):
            header.decompose()
        for footer in soup.find_all('footer'):
            footer.decompose()
        
        # Remove all elements where id or class contains "header" or "footer"
        def has_header_footer_in_attrs(element):
            """Check if element's id or class contains 'header' or 'footer'"""
            element_id = element.get('id', '') or ''
            element_class = element.get('class', [])
            if isinstance(element_class, list):
                element_class = ' '.join(element_class)
            else:
                element_class = str(element_class) or ''
            
            id_lower = element_id.lower()
            class_lower = element_class.lower()
            
            return 'header' in id_lower or 'footer' in id_lower or \
                   'header' in class_lower or 'footer' in class_lower
        
        elements_to_remove = []
        for element in soup.find_all(True):
            if has_header_footer_in_attrs(element):
                elements_to_remove.append(element)
        
        for element in elements_to_remove:
            element.decompose()
        
        # Enhanced pagination selectors - exact patterns from HTML
        pagination_selectors = [
            # EXACT patterns from the provided HTML
            'button[data-testid="goToNextPageBtn"]',  # Exact match
            'button[aria-label="Go to next page"]',   # Exact aria-label
            '.Paginator_btn__KRVdV',                  # Exact class
            'button[data-testid^="goToPage"]',        # Page number buttons
            # Backup patterns
            'button[data-testid*="nextPage"]',
            'button[aria-label*="next page" i]',
            '.pagination a',
            '.pager a',
            'a[href*="page"]',
            '.next-page',
            '[rel="next"]',
            '.page-numbers a',
            'button[class*="next"]',
            'button[class*="Next"]',
            'button:contains("Next")',
            'a:contains("Next")',
            'a:contains(">")',
            '[aria-label*="next" i]'
        ]
        
        print(f"Looking for pagination elements...")
        
        # First, try to find next page buttons/links
        next_page_element = None
        for selector in pagination_selectors:
            try:
                elements = soup.select(selector)
                print(f"Pagination selector '{selector}' found {len(elements)} elements")
                
                for element in elements:
                    # For buttons, we need to find the page URL differently
                    if element.name == 'button':
                        # Look for data attributes or onclick handlers that might contain page info
                        print(f"Found next page button: {element}")
                        next_page_element = element
                        break
                    else:
                        href = element.get('href')
                        if href:
                            print(f"Found next page link: {href}")
                            next_page_element = element
                            break
                
                if next_page_element:
                    break
            except Exception as e:
                print(f"Error with pagination selector '{selector}': {str(e)}")
                continue
        
        # If we found pagination, try to navigate through pages
        if next_page_element:
            print("Pagination detected, attempting to crawl multiple pages...")
            
            # For button-based pagination, we need to simulate clicks
            # This requires a more sophisticated approach with Playwright
            current_page = 1
            max_pages = 10
            visited_urls = {base_url}
            
            # Try to find numbered pagination links
            page_links = soup.find_all('a', href=re.compile(r'page=\d+|p=\d+|&page=\d+'))
            page_urls = []
            
            for link in page_links:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if full_url not in visited_urls:
                        page_urls.append(full_url)
                        visited_urls.add(full_url)
            
            # If no numbered pages found, try to construct page URLs
            if not page_urls:
                # Try common page URL patterns
                base_parsed = urlparse(base_url)
                for page_num in range(2, min(max_pages + 1, 11)):  # Pages 2-10
                    # Try different page parameter formats
                    page_patterns = [
                        f"{base_url}?page={page_num}",
                        f"{base_url}&page={page_num}",
                        f"{base_url}?p={page_num}",
                        f"{base_url}&p={page_num}",
                        f"{base_url}/page/{page_num}",
                        f"{base_url}/p{page_num}"
                    ]
                    
                    for pattern in page_patterns:
                        if pattern not in visited_urls:
                            page_urls.append(pattern)
                            visited_urls.add(pattern)
                            break  # Only try one pattern per page number
            
            print(f"Found {len(page_urls)} potential page URLs to crawl")
            
            # Crawl additional pages
            for page_num, page_url in enumerate(page_urls[:max_pages-1], 2):  # Start from page 2
                try:
                    # Check if page URL has already been scraped
                    if self._is_url_scraped(page_url):
                        print(f"⏭️ Skipping already scraped page {page_num}: {page_url}")
                        continue
                    
                    print(f"🔄 Crawling page {page_num}: {page_url}")
                    # Use Selenium to get HTML from additional pages
                    page_html = self._get_page_html_with_selenium(page_url, wait_for_elements=[
                        ".jobCardTitle", 
                        "[data-testid^='jobCardTitle_']", 
                        ".JobsList_jobCardTitle__pRNjw",
                        "a[href*='/job/']"
                    ], delay=10)
                    
                    if page_html:
                        # Mark page URL as scraped
                        self._mark_url_scraped(page_url)
                        page_job_links = await self._extract_job_links(page_html, base_url)
                        all_job_links.extend(page_job_links)
                        print(f"✅ Page {page_num} yielded {len(page_job_links)} job links")
                    else:
                        print(f"❌ Failed to crawl page {page_num}: {page_url}")
                        
                except Exception as e:
                    print(f"❌ Error crawling pagination page {page_num} {page_url}: {str(e)}")
                    continue
        else:
            print("No pagination elements found")
        
        print(f"Pagination crawling completed. Found {len(all_job_links)} additional job links")
        return all_job_links
    
    def _post_process_html_content(self, html_content: Optional[str]) -> Optional[str]:
        """
        Final HTML tweaks: remove ATS/vendor branding blocks and normalize a known
        header blue background to the app's Tailwind-style token.
        """
        if not html_content or not html_content.strip():
            return html_content
        original_html_content = html_content
        try:
            # Fix encoding artifacts: "Â" before non-breaking spaces (UTF-8 double-encoding)
            html_content = html_content.replace("\u00c2\u00a0", "\u00a0")  # Â + nbsp → nbsp
            html_content = html_content.replace("\u00c2 ", " ")            # Â + space → space
            # Standalone Â that shouldn't be there
            html_content = re.sub(r"\u00c2(?=\s|<|&)", "", html_content)

            soup = BeautifulSoup(html_content, "html.parser")
            self._remove_non_job_detail_sections(soup)
            for paragraph in list(soup.find_all("p")):
                text = paragraph.get_text("", strip=True).replace("\u00a0", "").strip()
                if not text and not paragraph.find(["img", "video", "iframe", "object", "embed", "br"]):
                    paragraph.decompose()
            # Replace background-color #2f5496 or its computed rgb(47, 84, 150)
            new_bg = "background-color: rgb(69 103 112 / var(--tw-bg-opacity, 1))"
            bg_color_pat = re.compile(
                r"background-color\s*:\s*(?:#2f5496\b|rgb\(\s*47\s*,\s*84\s*,\s*150\s*\))",
                re.I,
            )
            # Shorthand `background: #2f5496` or `background: rgb(47, 84, 150)`
            bg_shorthand_pat = re.compile(
                r"background\s*:\s*(?:#2f5496\b|rgb\(\s*47\s*,\s*84\s*,\s*150\s*\))(\s*!important)?",
                re.I,
            )
            for el in soup.find_all(style=True):
                style = el.get("style", "") or ""
                if not style:
                    continue
                updated = bg_color_pat.sub(new_bg, style)
                updated = bg_shorthand_pat.sub(new_bg, updated)
                if updated != style:
                    if "-webkit-text-fill-color" not in updated:
                        updated = updated.rstrip().rstrip(";") + "; -webkit-text-fill-color: white !important;"
                    el["style"] = updated
            processed_html = str(soup)
            if not processed_html.strip() and original_html_content.strip():
                logger.warning("html_content cleanup produced empty output; returning untrimmed content")
                return original_html_content
            return processed_html
        except Exception as e:
            logger.warning(f"html_content post-process skipped: {e}")
            return html_content

    def _remove_non_job_detail_sections(self, soup: BeautifulSoup) -> None:
        """
        Remove action controls, ATS branding, breadcrumbs, and related-job navigation
        from a detailed job page while preserving the main job description body.
        """
        action_text_re = re.compile(
            r"^\s*(apply(?:\s+now|\s+online|\s+for\s+this\s+job|\s+to\s+this\s+job)?|refer\s+to\s+a\s+friend)\W*$",
            re.I,
        )
        related_heading_re = re.compile(
            r"^\s*(similar|related|recommended)\s+jobs?\b|^\s*jobs\s+you\s+may\s+like\b|^\s*more\s+jobs\s+like\s+this\b",
            re.I,
        )
        jobs_nav_re = re.compile(
            r"^\s*(all\s+jobs|view\s+all\s+jobs|see\s+all\s+jobs|back\s+to\s+(?:all\s+)?jobs)\s*$",
            re.I,
        )
        related_attr_re = re.compile(
            r"(similar|related|recommended)[\s_-]*jobs?|jobs[\s_-]*you[\s_-]*may[\s_-]*like|all[\s_-]*jobs",
            re.I,
        )
        cookie_attr_re = re.compile(
            r"cookie(?:policy|banner|bar|consent|notice|wrapper)?|CookiePolicyBar|CookiePolicyBarWrapper|CookiePolicyBarButton",
            re.I,
        )
        apply_attr_re = re.compile(
            r"(?:^|[\s_-])(social[\s_-]*apply|dialogapplybtn|applyoption|applylistitemoption|"
            r"apply[\s_-]*(?:button|btn|container|link|option)|btn[\s_-]*social[\s_-]*apply)(?:$|[\s_-])|"
            r"/talentcommunity/apply/|start\s+applying|start\s+the\s+apply\s+process|"
            r"enter\s+email\s+to\s+start\s+application\s+process",
            re.I,
        )

        def element_attr_text(el) -> str:
            parts = []
            for attr in (
                "id",
                "class",
                "href",
                "aria-label",
                "title",
                "data-testid",
                "data-automation",
                "data-test",
                "data-ht",
                "placeholder",
                "action",
            ):
                value = el.get(attr)
                if isinstance(value, list):
                    parts.extend(str(item) for item in value)
                elif value:
                    parts.append(str(value))
            return " ".join(parts)

        def is_inline_hidden(el) -> bool:
            style = str(el.get("style") or "").lower()
            if not style:
                return False
            hidden_patterns = (
                r"display\s*:\s*none",
                r"visibility\s*:\s*hidden",
                r"opacity\s*:\s*0(?:\.0+)?(?:\s*;|$)",
                r"(?:^|;)\s*width\s*:\s*0(?:px|em|rem|%)?",
                r"(?:^|;)\s*height\s*:\s*0(?:px|em|rem|%)?",
            )
            return any(re.search(pattern, style) for pattern in hidden_patterns)

        for element in list(soup.find_all(True)):
            if not getattr(element, "parent", None):
                continue
            element_id = str(element.get("id", "")).strip().lower()
            if element_id in ("asbranding", "asbreadcrumbs"):
                element.decompose()
                continue
            attrs = element_attr_text(element)
            if cookie_attr_re.search(attrs):
                element.decompose()
                continue
            if is_inline_hidden(element):
                element.decompose()
                continue
            if apply_attr_re.search(attrs):
                block = self._select_apply_block(element)
                block.decompose()
                continue
            if related_attr_re.search(attrs):
                block = self._select_related_jobs_block(element)
                block.decompose()

        def is_cutoff(el) -> bool:
            if not getattr(el, "name", None):
                return False
            text = el.get_text(" ", strip=True)
            labels = " ".join(str(el.get(attr, "")) for attr in ("aria-label", "title", "value"))
            if (el.name in ("a", "button") or el.get("role") == "button") and (
                action_text_re.match(text or "") or action_text_re.match(labels.strip())
            ):
                return True
            if el.name == "input" and action_text_re.match(str(el.get("value", ""))):
                return True
            return False

        def text_len(el) -> int:
            return len(el.get_text(" ", strip=True)) if getattr(el, "get_text", None) else 0

        def select_action_block(el):
            block = el
            for parent in el.parents:
                if not getattr(parent, "name", None) or parent.name in ("[document]", "body", "main"):
                    break
                if parent.name not in ("div", "section", "aside", "form", "p", "li"):
                    continue
                parent_text = parent.get_text(" ", strip=True)
                action_only = re.fullmatch(
                    r"(?is)\s*(apply(?:\s+now|\s+online|\s+for\s+this\s+job|\s+to\s+this\s+job)?|refer\s+to\s+a\s+friend)\W*(\s+(apply(?:\s+now|\s+online|\s+for\s+this\s+job|\s+to\s+this\s+job)?|refer\s+to\s+a\s+friend)\W*)*\s*",
                    parent_text or "",
                )
                has_content_children = bool(parent.find(
                    ["h1", "h2", "h3", "h4", "p", "ul", "ol", "table", "article"],
                    recursive=True,
                ))
                # Do not climb into the full job body. Action wrappers are small
                # and contain only action text/buttons; content wrappers have real
                # headings, paragraphs, lists, or tables.
                if text_len(parent) > 250 or has_content_children or not action_only:
                    break
                block = parent
            return block

        for el in list(soup.find_all(True)):
            if not getattr(el, "parent", None):
                continue
            if not is_cutoff(el):
                continue

            block = select_action_block(el)
            block.decompose()

        for el in list(soup.find_all(True)):
            if not getattr(el, "parent", None):
                continue
            text = el.get_text(" ", strip=True)
            if related_heading_re.match(text or "") or jobs_nav_re.match(text or ""):
                block = self._select_related_jobs_block(el)
                block.decompose()

    def _select_apply_block(self, el):
        """Choose the apply/social-apply wrapper without climbing into the job body."""
        apply_container_re = re.compile(
            r"(social[\s_-]*apply[\s_-]*button[\s_-]*container|btn[\s_-]*social[\s_-]*apply|"
            r"socialbutton|emailgetter|applylistitemoption|applyoption|dialogapplybtn)",
            re.I,
        )
        block = el
        for parent in el.parents:
            if not getattr(parent, "name", None) or parent.name in ("[document]", "body", "main", "article"):
                break
            parent_attrs = " ".join(
                str(parent.get(attr, ""))
                for attr in ("id", "class", "aria-label", "title", "data-testid", "data-automation", "data-test")
            )
            parent_text = parent.get_text(" ", strip=True)
            if apply_container_re.search(parent_attrs):
                block = parent
                continue
            if parent.name in ("div", "section", "aside", "form", "ul", "li") and len(parent_text) <= 1200:
                block = parent
                continue
            break
        return block

    def _select_related_jobs_block(self, el):
        """Choose a small related-jobs/navigation container without climbing into the main body."""
        job_body_re = re.compile(
            r"\b(job\s+description|responsibilities|qualifications|requirements|required\s+experience|"
            r"skills|benefits|about\s+the\s+role|purpose\s+of\s+the\s+role)\b",
            re.I,
        )
        block = el
        for parent in el.parents:
            if not getattr(parent, "name", None) or parent.name in ("[document]", "body", "main", "article"):
                break
            parent_text = parent.get_text(" ", strip=True)
            if len(parent_text) > 800 and job_body_re.search(parent_text):
                break
            parent_attrs = " ".join(
                str(parent.get(attr, ""))
                for attr in ("id", "class", "aria-label", "title", "data-testid", "data-automation", "data-test")
            )
            if parent.name in ("section", "aside", "nav") or re.search(
                r"(similar|related|recommended)[\s_-]*jobs?|all[\s_-]*jobs",
                parent_attrs,
                re.I,
            ):
                if len(parent_text) > 800 and job_body_re.search(parent_text):
                    break
                block = parent
                break
            if parent.name in ("div", "ul", "ol", "li") and len(parent_text) <= 1500:
                block = parent
                continue
            break
        return block

    async def _extract_html_content_with_styles(self, html: str, base_url: str) -> Optional[str]:
        """
        Extract main body HTML content with optimized inline styles.
        Excludes header and footer, and inlines only necessary computed styles.
        Optimizes by removing duplicate and unnecessary styles.
        """
        try:
            # Use Selenium to get computed styles from the browser
            driver = None
            try:
                driver = self._setup_selenium_driver()
                self._selenium_navigate(driver, base_url)
                self._accept_cookie_banner_if_present(driver)
                
                # Keep this close to the original working renderer: let the detail
                # page settle, then scroll once so lazy sections compute their styles.
                time.sleep(2)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                
                # Get HTML with optimized inline styles
                html_content = driver.execute_script("""
                    // Default values that don't need to be inlined (browser defaults)
                    const defaultValues = {
                        'color': 'rgb(0, 0, 0)',
                        'background-color': 'rgba(0, 0, 0, 0)',
                        'background': 'rgba(0, 0, 0, 0) none repeat scroll 0% 0% / auto padding-box border-box',
                        'font-family': 'serif',
                        'font-size': '16px',
                        'font-weight': '400',
                        'font-style': 'normal',
                        'line-height': 'normal',
                        'text-align': 'start',
                        'text-decoration': 'none',
                        'text-transform': 'none',
                        'letter-spacing': 'normal',
                        'word-spacing': 'normal',
                        'border': '0px none rgb(0, 0, 0)',
                        'border-width': '0px',
                        'border-style': 'none',
                        'border-color': 'rgb(0, 0, 0)',
                        'border-radius': '0px',
                        'margin': '0px',
                        'padding': '0px',
                        'width': 'auto',
                        'height': 'auto',
                        'display': 'block',
                        'position': 'static',
                        'float': 'none',
                        'clear': 'none',
                        'overflow': 'visible',
                        'visibility': 'visible',
                        'opacity': '1',
                        'box-sizing': 'content-box',
                        'box-shadow': 'none',
                        'outline': '0px',
                        'text-shadow': 'none',
                        'white-space': 'normal',
                        'vertical-align': 'baseline',
                        'list-style': 'disc outside none',
                        'transform': 'none',
                        'transition': 'none 0s ease 0s',
                        'animation': 'none 0s ease 0s 1 normal none running'
                    };
                    
                    // Function to check if a value is effectively default
                    function isDefaultValue(prop, value) {
                        const defaultValue = defaultValues[prop];
                        if (!defaultValue) return false;
                        
                        // Normalize values for comparison
                        const normalize = (val) => val.toLowerCase().replace(/\\s+/g, ' ').trim();
                        return normalize(value) === normalize(defaultValue);
                    }
                    
                    // Function to get optimized computed styles for an element
                    function getOptimizedStyles(element) {
                        const styles = window.getComputedStyle(element);
                        const styleObj = {};
                        
                        // Get all CSS properties from computed style
                        const allProperties = new Set();
                        for (let i = 0; i < styles.length; i++) {
                            allProperties.add(styles[i]);
                        }
                        
                        // Also include important visual properties
                        const importantProps = [
                            'color', 'background-color', 'background', 'background-image', 
                            'background-position', 'background-repeat', 'background-size',
                            'font-family', 'font-size', 'font-weight', 'font-style', 
                            'line-height', 'text-align', 'text-decoration', 'text-transform',
                            'letter-spacing', 'word-spacing',
                            'border', 'border-width', 'border-style', 'border-color',
                            'border-top', 'border-right', 'border-bottom', 'border-left',
                            'border-radius', 'border-top-left-radius', 'border-top-right-radius',
                            'border-bottom-left-radius', 'border-bottom-right-radius',
                            'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
                            'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
                            'width', 'height', 'min-width', 'min-height', 'max-width', 'max-height',
                            'display', 'position', 'top', 'right', 'bottom', 'left', 'z-index',
                            'float', 'clear', 'overflow', 'overflow-x', 'overflow-y',
                            'visibility', 'opacity', 'cursor',
                            'box-sizing', 'box-shadow', 'outline', 'outline-width', 
                            'outline-style', 'outline-color',
                            'flex', 'flex-direction', 'flex-wrap', 'flex-grow', 'flex-shrink',
                            'flex-basis', 'justify-content', 'align-items', 'align-content',
                            'align-self', 'order', 'gap', 'row-gap', 'column-gap',
                            'grid', 'grid-template-columns', 'grid-template-rows',
                            'grid-column', 'grid-row',
                            'text-shadow', 'white-space', 'word-wrap', 'word-break',
                            'vertical-align', 'list-style', 'list-style-type',
                            'transform', 'transform-origin'
                        ];
                        
                        importantProps.forEach(prop => allProperties.add(prop));
                        
                        // Filter and collect only non-default, meaningful styles
                        for (const prop of allProperties) {
                            try {
                                const value = styles.getPropertyValue(prop);
                                if (value && value.trim() !== '') {
                                    // Skip default values
                                    if (!isDefaultValue(prop, value)) {
                                        // Skip empty or transparent values for certain properties
                                        if (prop === 'background-color' || prop === 'background') {
                                            if (value.includes('rgba(0, 0, 0, 0)') || value.includes('transparent')) {
                                                continue;
                                            }
                                        }
                                        // Skip 'none' for certain properties
                                        if ((prop.includes('shadow') || prop.includes('outline') || prop === 'border') && 
                                            value.toLowerCase().includes('none') && !value.toLowerCase().includes('0px')) {
                                            continue;
                                        }
                                        styleObj[prop] = value;
                                    }
                                }
                            } catch (e) {
                                // Skip properties that can't be accessed
                            }
                        }
                        
                        return styleObj;
                    }
                    
                    // Convert style object to optimized CSS string
                    function styleObjToCss(styleObj) {
                        // Sort properties for consistency (helps with deduplication)
                        const sortedProps = Object.keys(styleObj).sort();
                        let css = '';
                        for (const prop of sortedProps) {
                            css += prop + ':' + styleObj[prop] + ';';
                        }
                        return css;
                    }
                    
                    // Cache for style strings to avoid duplicates
                    const styleCache = new Map();
                    
                    // Function to inline optimized styles into an element
                    function inlineOptimizedStyles(element) {
                        // Skip script and style tags
                        if (element.tagName === 'SCRIPT' || element.tagName === 'STYLE') {
                            return;
                        }
                        
                        const styles = getOptimizedStyles(element);
                        
                        if (Object.keys(styles).length === 0) {
                            // No meaningful styles, remove inline style if exists
                            element.removeAttribute('style');
                            // Process children
                            Array.from(element.children).forEach(inlineOptimizedStyles);
                            return;
                        }
                        
                        // Convert to CSS string
                        const styleString = styleObjToCss(styles);
                        
                        // Check cache for identical styles (optimization)
                        let finalStyle = styleCache.get(styleString);
                        if (!finalStyle) {
                            // Format with spaces for readability (but still compact)
                            finalStyle = styleString.replace(/;/g, '; ').trim();
                            styleCache.set(styleString, finalStyle);
                        }
                        
                        // Set inline style
                        element.setAttribute('style', finalStyle);
                        
                        // Process children
                        Array.from(element.children).forEach(inlineOptimizedStyles);
                    }
                    
                    // Remove header and footer tags
                    const headers = document.querySelectorAll('header, footer');
                    headers.forEach(el => el.remove());
                    
                    // Remove all elements where id or class contains "header" or "footer"
                    function hasHeaderFooter(element) {
                        const id = (element.getAttribute('id') || '').toLowerCase();
                        const className = (element.getAttribute('class') || '').toLowerCase();
                        return id.includes('header') || id.includes('footer') ||
                               className.includes('header') || className.includes('footer');
                    }
                    
                    // Remove search controls; action buttons are handled by post-process cutoff.
                    function shouldRemoveElement(element) {
                        const id = element.getAttribute('id') || '';
                        const className = element.getAttribute('class') || '';
                        const role = element.getAttribute('role') || '';
                        const aria = element.getAttribute('aria-label') || '';
                        const idLower = id.toLowerCase();
                        const classLower = className.toLowerCase();
                        const attrText = [idLower, classLower, role.toLowerCase(), aria.toLowerCase()].join(' ');
                        return idLower.includes('search') || classLower.includes('search')
                            || /cookie(policy|banner|bar|consent|notice|wrapper)?/.test(attrText)
                            || id === 'CookiePolicyBarWrapper'
                            || id === 'CookiePolicyBar'
                            || id === 'CookiePolicyBarButton';
                    }

                    function shouldRemoveRenderedElement(element) {
                        if (!element || element === document.body || element === document.documentElement) {
                            return false;
                        }
                        const tag = (element.tagName || '').toLowerCase();
                        if (tag === 'script' || tag === 'style' || tag === 'noscript') {
                            return true;
                        }
                        const style = window.getComputedStyle(element);
                        if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
                            return true;
                        }
                        const rect = element.getBoundingClientRect();
                        return rect.width === 0 || rect.height === 0;
                    }
                    
                    // Remove matching elements
                    const allElements = document.querySelectorAll('*');
                    const elementsToRemove = [];
                    allElements.forEach(el => {
                        if (hasHeaderFooter(el) || shouldRemoveElement(el) || shouldRemoveRenderedElement(el)) {
                            elementsToRemove.push(el);
                        }
                    });
                    elementsToRemove.forEach(el => el.remove());
                    
                    // Remove branding elements (e.g. SilkRoad "asbranding")
                    const brandingEl = document.getElementById('asbranding');
                    if (brandingEl) brandingEl.remove();
                    
                    // Try to find main content area
                    let mainContent = null;
                    const selectors = [
                        'main', '[role="main"]', '.main-content', '.content',
                        '.job-content', '.job-details', '.job-description',
                        '#main', '#content', '#job-content', '.jobDisplayShell',
                        '.job-posting', '.job-detail'
                    ];
                    
                    for (const selector of selectors) {
                        mainContent = document.querySelector(selector);
                        if (mainContent) break;
                    }
                    
                    if (!mainContent) {
                        mainContent = document.body;
                    }
                    
                    // Inline optimized styles recursively
                    inlineOptimizedStyles(mainContent);
                    
                    // Replace background-color rgb(47, 84, 150) (computed from #2f5496)
                    // with the app's Tailwind token
                    const newBg = 'rgb(69, 103, 112)';
                    function replaceBgColor(el) {
                        const style = el.getAttribute('style');
                        if (style && /background-color\s*:\s*rgb\(47,\s*84,\s*150\)/.test(style)) {
                            let updated = style.replace(/background-color\s*:\s*rgb\(47,\s*84,\s*150\)/g, 'background-color: ' + newBg);
                            updated += ' -webkit-text-fill-color: white !important;';
                            el.setAttribute('style', updated);
                        }
                        Array.from(el.children).forEach(replaceBgColor);
                    }
                    replaceBgColor(mainContent);
                    
                    // Remove branding inside mainContent as well
                    const brandingInMain = mainContent.querySelector('#asbranding');
                    if (brandingInMain) brandingInMain.remove();
                    
                    // Return the HTML
                    return mainContent.outerHTML;
                """)
                
                logger.info(f"Extracted HTML content with optimized inline styles: {len(html_content)} characters")
                return self._post_process_html_content(html_content)
                
            finally:
                self._selenium_quit_safe(driver)
                    
        except Exception as e:
            logger.error(f"Error extracting HTML content with styles using Selenium: {str(e)}")
            # Fallback to the original method if Selenium fails
            try:
                return await self._extract_html_content_with_styles_fallback(html, base_url)
            except Exception as e2:
                logger.error(f"Fallback method also failed: {str(e2)}")
                return None
    
    async def _extract_html_content_with_styles_fallback(self, html: str, base_url: str) -> Optional[str]:
        """
        Fallback method to extract HTML content with styles using CSS parsing.
        Used when Selenium is not available or fails.
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove header and footer elements
            for element in soup.find_all(['header', 'footer']):
                element.decompose()
            
            # Remove all elements where id or class contains "header" or "footer"
            def has_header_footer_in_attrs(element):
                """Check if element's id or class contains 'header' or 'footer'"""
                element_id = element.get('id', '') or ''
                element_class = element.get('class', [])
                if isinstance(element_class, list):
                    element_class = ' '.join(element_class)
                else:
                    element_class = str(element_class) or ''
                
                id_lower = element_id.lower()
                class_lower = element_class.lower()
                
                return 'header' in id_lower or 'footer' in id_lower or \
                       'header' in class_lower or 'footer' in class_lower
            
            elements_to_remove = []
            for element in soup.find_all(True):
                if has_header_footer_in_attrs(element):
                    elements_to_remove.append(element)
            
            for element in elements_to_remove:
                element.decompose()
            
            # Remove search controls; action buttons are handled by post-process cutoff.
            for element in soup.find_all(True):
                element_id = element.get('id', '') or ''
                element_class = element.get('class', [])
                if isinstance(element_class, list):
                    element_class = ' '.join(element_class)
                else:
                    element_class = str(element_class) or ''
                
                id_lower = element_id.lower()
                class_lower = element_class.lower()
                
                if 'search' in id_lower or 'search' in class_lower:
                    element.decompose()
            
            # Try to find the main content area
            main_content = None
            
            # Common selectors for main content
            main_selectors = [
                'main',
                '[role="main"]',
                '.main-content',
                '.content',
                '.job-content',
                '.job-details',
                '.job-description',
                '#main',
                '#content',
                '#job-content',
                '.jobDisplayShell',  # Common job display container
                '.job-posting',
                '.job-detail'
            ]
            
            for selector in main_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    logger.info(f"Found main content using selector: {selector}")
                    break
            
            # If no main content found, use body but exclude header/footer
            if not main_content:
                body = soup.find('body')
                if body:
                    # Remove header and footer from body if they still exist
                    for element in body.find_all(['header', 'footer']):
                        element.decompose()
                    main_content = body
                else:
                    main_content = soup
            
            # Extract and download CSS files
            css_rules = await self._extract_and_parse_css(soup, base_url)
            
            # Inline CSS styles into HTML elements
            if css_rules:
                self._inline_css_styles(main_content, css_rules)
            
            # Convert to string
            html_content = str(main_content)
            
            logger.info(f"Extracted HTML content (fallback): {len(html_content)} characters")
            return self._post_process_html_content(html_content)
            
        except Exception as e:
            logger.error(f"Error in fallback HTML extraction: {str(e)}")
            return None

    def _extract_plain_html_content_fallback(self, html: str) -> str:
        """Last-resort detail HTML fallback so API responses still include html_content."""
        try:
            soup = BeautifulSoup(html or "", "html.parser")
            for element in soup(["script", "style", "noscript", "header", "footer"]):
                element.decompose()

            main_content = None
            for selector in (
                "main",
                "[role='main']",
                ".job-content",
                ".job-details",
                ".job-description",
                "#job-content",
                ".jobDisplayShell",
                ".job-posting",
                ".job-detail",
                "article",
            ):
                main_content = soup.select_one(selector)
                if main_content:
                    break

            if not main_content:
                main_content = soup.find("body") or soup

            self._remove_non_job_detail_sections(main_content)
            cleaned = self._post_process_html_content(str(main_content))
            return cleaned or ""
        except Exception as e:
            logger.warning(f"Plain html_content fallback failed: {e}")
            return ""
    
    async def _extract_and_parse_css(self, soup: BeautifulSoup, base_url: str) -> Dict:
        """
        Extract CSS files from the HTML and parse them into a dictionary of rules.
        Returns a dict mapping selectors to style properties.
        """
        css_rules = {}
        
        try:
            # Find all link tags with rel="stylesheet"
            css_links = soup.find_all('link', rel='stylesheet')
            
            # Also find style tags with inline CSS
            style_tags = soup.find_all('style')
            
            async with aiohttp.ClientSession() as session:
                # Download external CSS files
                for link in css_links:
                    href = link.get('href')
                    if href:
                        css_url = urljoin(base_url, href)
                        try:
                            async with session.get(css_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                                if response.status == 200:
                                    css_content = await response.text()
                                    parsed_rules = self._parse_css_rules(css_content)
                                    css_rules.update(parsed_rules)
                                    logger.info(f"Downloaded and parsed CSS from: {css_url}")
                        except Exception as e:
                            logger.warning(f"Failed to download CSS from {css_url}: {str(e)}")
                            continue
                
                # Parse inline style tags
                for style_tag in style_tags:
                    if style_tag.string:
                        parsed_rules = self._parse_css_rules(style_tag.string)
                        css_rules.update(parsed_rules)
                        logger.info("Parsed inline style tag")
            
            logger.info(f"Total CSS rules extracted: {len(css_rules)}")
            return css_rules
            
        except Exception as e:
            logger.error(f"Error extracting CSS: {str(e)}")
            return css_rules
    
    def _parse_css_rules(self, css_content: str) -> Dict:
        """
        Parse CSS content and return a dictionary mapping selectors to style properties.
        """
        css_rules = {}
        
        try:
            # Use cssutils to parse CSS
            sheet = cssutils.parseString(css_content)
            
            for rule in sheet:
                if rule.type == rule.STYLE_RULE:
                    selector = rule.selectorText
                    styles = {}
                    
                    for prop in rule.style:
                        property_name = prop.name
                        property_value = prop.value
                        styles[property_name] = property_value
                    
                    if selector and styles:
                        # Handle multiple selectors (comma-separated)
                        selectors = [s.strip() for s in selector.split(',')]
                        for sel in selectors:
                            if sel in css_rules:
                                # Merge with existing rules
                                css_rules[sel].update(styles)
                            else:
                                css_rules[sel] = styles.copy()
            
        except Exception as e:
            logger.warning(f"Error parsing CSS: {str(e)}")
            # Fallback: simple regex-based parsing for basic cases
            try:
                # Match CSS rules with regex
                pattern = r'([^{]+)\{([^}]+)\}'
                matches = re.findall(pattern, css_content, re.DOTALL)
                
                for selector, properties in matches:
                    selector = selector.strip()
                    if not selector:
                        continue
                    
                    styles = {}
                    # Parse properties
                    prop_pattern = r'([^:]+):([^;]+);?'
                    prop_matches = re.findall(prop_pattern, properties)
                    
                    for prop_name, prop_value in prop_matches:
                        prop_name = prop_name.strip()
                        prop_value = prop_value.strip()
                        if prop_name and prop_value:
                            styles[prop_name] = prop_value
                    
                    if selector and styles:
                        selectors = [s.strip() for s in selector.split(',')]
                        for sel in selectors:
                            if sel in css_rules:
                                css_rules[sel].update(styles)
                            else:
                                css_rules[sel] = styles.copy()
            except Exception as e2:
                logger.warning(f"Fallback CSS parsing also failed: {str(e2)}")
        
        return css_rules
    
    def _inline_css_styles(self, element, css_rules: Dict):
        """
        Inline CSS styles into HTML elements based on their classnames and IDs.
        """
        try:
            # Process all elements in the tree
            for tag in element.find_all(True):
                inline_styles = {}
                
                # Get existing inline styles
                existing_style = tag.get('style', '')
                if existing_style:
                    # Parse existing inline styles
                    for style_pair in existing_style.split(';'):
                        if ':' in style_pair:
                            prop, value = style_pair.split(':', 1)
                            inline_styles[prop.strip()] = value.strip()
                
                # Get element's classes and ID
                classes = tag.get('class', [])
                if isinstance(classes, str):
                    classes = [classes]
                element_id = tag.get('id', '')
                tag_name = tag.name
                
                # Apply CSS rules based on selectors
                for selector, styles in css_rules.items():
                    # Check if this element matches the selector
                    if self._element_matches_selector(tag, selector, classes, element_id, tag_name):
                        # Merge styles (selector-specific styles override existing)
                        for prop, value in styles.items():
                            inline_styles[prop] = value
                
                # Convert inline_styles back to style attribute string
                if inline_styles:
                    style_string = '; '.join([f"{prop}: {value}" for prop, value in inline_styles.items()])
                    tag['style'] = style_string
                
        except Exception as e:
            logger.warning(f"Error inlining CSS styles: {str(e)}")
    
    def _element_matches_selector(self, element, selector: str, classes: List[str], element_id: str, tag_name: str) -> bool:
        """
        Check if an element matches a CSS selector.
        Supports: tag names, .class, #id, and combinations.
        """
        try:
            # Normalize selector
            selector = selector.strip()
            if not selector:
                return False
            
            # Handle descendant selectors (e.g., "div .class") - for now, just check the last part
            if ' ' in selector:
                parts = selector.split()
                if len(parts) > 1:
                    # Check if the last part matches this element
                    return self._element_matches_selector(element, parts[-1], classes, element_id, tag_name)
            
            # Handle class selectors (e.g., ".class", ".class1.class2")
            if selector.startswith('.'):
                class_names = [c.strip() for c in selector[1:].split('.') if c.strip()]
                if class_names and all(cn in classes for cn in class_names):
                    return True
            
            # Handle ID selectors (e.g., "#id")
            elif selector.startswith('#'):
                id_name = selector[1:].strip()
                if element_id == id_name:
                    return True
            
            # Handle tag selectors (e.g., "div")
            elif selector == tag_name:
                return True
            
            # Handle combined selectors (e.g., "div.class", "div#id")
            elif '.' in selector or '#' in selector:
                # Tag with class (e.g., "div.class")
                if '.' in selector and not selector.startswith('.'):
                    parts = selector.split('.', 1)
                    if len(parts) == 2:
                        tag_part = parts[0].strip()
                        class_part = parts[1].strip()
                        if tag_part == tag_name and class_part in classes:
                            return True
                
                # Tag with ID (e.g., "div#id")
                if '#' in selector and not selector.startswith('#'):
                    parts = selector.split('#', 1)
                    if len(parts) == 2:
                        tag_part = parts[0].strip()
                        id_part = parts[1].strip()
                        if tag_part == tag_name and element_id == id_part:
                            return True
                
                # Multiple classes without tag (e.g., ".class1.class2")
                if selector.count('.') > 1 and selector.startswith('.'):
                    class_parts = [c.strip() for c in selector[1:].split('.') if c.strip()]
                    if all(cp in classes for cp in class_parts):
                        return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error matching selector '{selector}': {str(e)}")
            return False
    
    async def _scrape_individual_job_with_crawl4ai(
        self,
        job_url: str,
        crawler: Optional[AsyncWebCrawler] = None,
    ) -> Optional[Dict]:
        """Scrape individual job details using Crawl4AI and OpenAI for extraction"""
        try:
            logger.info(f"Scraping job with Crawl4AI: {job_url}")
            
            # Use the shared crawler from scrape_jobs when available. Creating a fresh
            # crawler/browser per job is one of the biggest latency costs.
            detail_delay = 2
            detail_page_timeout = 45000 if self.fast_mode else 60000
            if crawler is not None:
                result = await crawler.arun(
                    url=job_url,
                    delay_before_return_html=detail_delay,
                    timeout=30000,
                    page_timeout=detail_page_timeout
                )
            else:
                async with AsyncWebCrawler(verbose=False) as local_crawler:
                    result = await local_crawler.arun(
                        url=job_url,
                        delay_before_return_html=detail_delay,
                        timeout=30000,
                        page_timeout=detail_page_timeout
                    )
            
            if not result.success:
                logger.error(f"Failed to crawl job page: {job_url}")
                return None
            
            # Save HTML for debugging
            if hasattr(result, 'html') and result.html:
                self._save_html_debug(result.html, job_url, "individual_job")
            
            # Use OpenAI to extract structured data from the HTML
            job_data = await self._extract_job_data_with_ai(result.html, job_url)
            
            if self.include_html_content:
                # Use browser-computed styles for accurate rendering. The fallback
                # CSS parser is faster but can miss complex external/ATS styles.
                html_content = await self._extract_html_content_with_styles(result.html, job_url)
                if not html_content:
                    logger.warning(f"Styled html_content extraction returned empty for {job_url}; using plain fallback")
                    html_content = self._extract_plain_html_content_fallback(result.html)
                job_data["html_content"] = html_content or ""
            
            return job_data
                
        except Exception as e:
            logger.error(f"Error scraping job {job_url}: {str(e)}")
            return None
    
    async def _extract_job_data_with_ai(self, html: str, job_url: str) -> Dict:
        """Use OpenAI to extract structured job data from HTML"""
        
        # Clean and truncate HTML to fit within token limits
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        self._remove_non_job_detail_sections(soup)
        
        # Get text content and limit length. A 4k character cutoff often misses
        # qualifications/benefits on longer ATS pages, so keep a larger window.
        text_content = soup.get_text(separator="\n", strip=True)
        max_ai_chars = int(os.getenv("AI_EXTRACTION_MAX_CHARS", "8000"))
        if len(text_content) > max_ai_chars:
            text_content = text_content[:max_ai_chars] + "..."

        category_options = self._format_categories_for_prompt()
        
        prompt = f"""
        Extract job information from the following job posting content. Return the data as a JSON object with these exact fields:

        - employer: Company/organization name
        - job_title: Job position title
        - job_id: Job ID or reference number if available
        - job_description: Brief job description/summary
        - location: Standard job location as "city/town, province/state, country"
        - city: Job city or town
        - state: Job province or state
        - country: Job country
        - salary_range: Salary range or compensation details
        - application_deadline: Application deadline date
        - image_url: Company logo or job-related image URL
        - key_responsibilities: Main job responsibilities
        - qualifications_and_skills: Required qualifications and skills
        - required_experience: Required experience, minimum qualifications, required qualifications/skills, or required competencies (text description of what experience is needed)
        - perks_and_benefits: Job benefits and perks
        - preferred_years_of_experience: Years of experience required/preferred
        - educational_level: Education requirements
        - certification_level: Required certifications
        - interview_format: Interview process information
        - category_id: The id of exactly one child/leaf category selected from the category list below
        - category_name: The name of exactly one child/leaf category selected from the category list below

        Job URL: {job_url}

        Child/leaf category list. Choose exactly one from this list only. Do not choose a parent category:
        {category_options}
        
        Job Content:
        {text_content}
        
        Return only valid JSON. If a field is not found, use null as the value.
        Normalize location to city/town, province/state, country. If the source page omits country, infer it from the province/state or city when obvious. If the source page omits province/state, infer it from the city when obvious.
        For category_id and category_name, choose the single best matching child/leaf category from the category list. If the job is only test/dummy/sample content, return the child category named Test when it exists; otherwise return Other. If no child category matches this job, return the child category named Other. Do not invent a category and do not return a parent category.
        """
        
        try:
            response = await self.openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
                messages=[
                    {"role": "system", "content": "You are a job data extraction assistant. Extract job information and return it as valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1800,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            
            # Try to parse JSON from the response
            try:
                # Remove any markdown code blocks
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                
                job_data = json.loads(content)
                
                # Convert all fields to strings to match Pydantic model
                cleaned_data = {}
                for key, value in job_data.items():
                    if isinstance(value, list):
                        # Convert list to string (join with newlines)
                        cleaned_data[key] = '\n'.join(str(item) for item in value)
                    elif isinstance(value, dict):
                        # Convert dict to string representation
                        cleaned_data[key] = json.dumps(value, indent=2)
                    elif value is None:
                        cleaned_data[key] = ""
                    else:
                        cleaned_data[key] = str(value)

                self._normalize_extracted_category(cleaned_data)
                self._standardize_location_fields(cleaned_data)
                
                cleaned_data["source_url"] = job_url  # Add the job URL
                return cleaned_data
                
            except json.JSONDecodeError:
                # If JSON parsing fails, return a basic structure
                return {
                    "employer": "",
                    "job_title": "",
                    "job_id": "",
                    "job_description": text_content[:200] + "..." if len(text_content) > 200 else text_content,
                    "location": "",
                    "city": "",
                    "state": "",
                    "country": "",
                    "salary_range": "",
                    "application_deadline": "",
                    "image_url": "",
                    "key_responsibilities": "",
                    "qualifications_and_skills": "",
                    "required_experience": "",
                    "perks_and_benefits": "",
                    "preferred_years_of_experience": "",
                    "educational_level": "",
                    "certification_level": "",
                    "interview_format": "",
                    "category_id": "",
                    "category_name": "",
                    "source_url": job_url
                }
                
        except Exception as e:
            print(f"Error with OpenAI API: {str(e)}")
            # Return basic structure if AI extraction fails
            return {
                "employer": "",
                "job_title": "Job Title Not Found",
                "job_id": "",
                    "job_description": text_content[:200] + "..." if len(text_content) > 200 else text_content,
                    "location": "",
                    "city": "",
                    "state": "",
                    "country": "",
                    "salary_range": "",
                "application_deadline": "",
                "image_url": "",
                "key_responsibilities": "",
                "qualifications_and_skills": "",
                "required_experience": "",
                "perks_and_benefits": "",
                "preferred_years_of_experience": "",
                "educational_level": "",
                "certification_level": "",
                "interview_format": "",
                "category_id": "",
                "category_name": "",
                "source_url": job_url
            }
