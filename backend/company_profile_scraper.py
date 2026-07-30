import json
import os
import re
from typing import Dict, List, Optional
from urllib.parse import unquote, urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup, Tag
from openai import AsyncOpenAI


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CONTACT_KEYS = {
    "name",
    "address",
    "city",
    "post_code",
    "state",
    "country",
    "telephone",
    "phone",
    "fax",
    "mail",
    "contact_person",
}

CONTACT_FIELD_NAMES = [
    "name",
    "address",
    "city",
    "post_code",
    "state",
    "country",
    "telephone",
    "phone",
    "fax",
    "mail",
    "contact_person",
]

CONTACT_PERSON_FIELD_NAMES = [
    "name",
    "email",
    "phone",
    "telephone",
    "fax",
]

COUNTRY_NAMES = {
    "canada",
    "united states",
    "usa",
    "us",
    "mexico",
    "australia",
    "united kingdom",
    "uk",
    "germany",
    "sweden",
    "finland",
    "france",
    "spain",
    "italy",
    "brazil",
    "chile",
    "peru",
    "south africa",
    "india",
    "china",
}


async def scrape_company_pages(
    home_page_url: str,
    contact_us_url: Optional[str],
    about_us_url: str,
) -> Dict:
    has_contact_url = bool(contact_us_url and contact_us_url.strip())
    pages_to_fetch = [
        ("home_page", home_page_url),
        ("about_us_page", about_us_url),
    ]
    if has_contact_url:
        pages_to_fetch.insert(1, ("contact_us_page", contact_us_url.strip()))

    page_results = await _fetch_pages(
        pages_to_fetch
    )
    pages = {result["page"]: result for result in page_results}
    errors = [
        {
            "page": result["page"],
            "url": result["url"],
            "status_code": result.get("status_code"),
            "error": result["error"],
        }
        for result in page_results
        if result.get("error")
    ]
    openai_client = _build_openai_client()

    home_data = parse_home_page(pages["home_page"].get("html") or "", home_page_url)
    about_data = await parse_about_page_with_ai(
        pages["about_us_page"].get("html") or "",
        about_us_url,
        openai_client,
    )
    contact_html = (
        pages["contact_us_page"].get("html")
        if has_contact_url and "contact_us_page" in pages
        else pages["home_page"].get("html")
    ) or ""
    contact_base_url = contact_us_url.strip() if has_contact_url else home_page_url
    contact_regions = await parse_contact_page_with_ai(
        contact_html,
        contact_base_url,
        openai_client,
    )

    return {
        "home_page": home_data,
        "about_us_page": about_data,
        "contact_us_page": {
            "regions": contact_regions,
        },
        "errors": errors,
    }


async def _fetch_pages(pages: List[tuple]) -> List[Dict]:
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout, headers=REQUEST_HEADERS) as session:
        return [await _fetch_page(session, page, url) for page, url in pages]


async def _fetch_page(session: aiohttp.ClientSession, page: str, url: str) -> Dict:
    try:
        async with session.get(url, allow_redirects=True) as response:
            html = await response.text()
            error = None
            if response.status >= 400:
                error = f"HTTP {response.status}"
            return {
                "page": page,
                "url": str(response.url),
                "status_code": response.status,
                "html": html,
                "error": error,
            }
    except Exception as e:
        return {
            "page": page,
            "url": url,
            "status_code": None,
            "html": "",
            "error": str(e),
        }


def parse_home_page(html: str, base_url: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
    document_base_url = _document_base_url(soup, base_url)
    main_content = _find_middle_content(soup) or soup
    hero = main_content.select_one(".n-anons") or soup.select_one(".n-anons")

    return {
        "company_logo": _absolute_url(_first_img_src(soup.select_one(".logobox")), document_base_url),
        "company_name": _clean_text(
            (main_content.select_one("h1.bold") or main_content.select_one("h1") or soup.select_one("h1"))
        ),
        "hero_image": _absolute_url(_first_img_src(hero), document_base_url),
        "description": _clean_text(hero),
        "tags": _parse_tags(soup),
        "sections": _parse_sections(soup, document_base_url),
    }


def parse_about_page(html: str, base_url: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
    document_base_url = _document_base_url(soup, base_url)
    content = (
        soup.select_one(".n-anons")
        or _find_middle_content(soup)
        or soup.select_one("article")
        or soup.select_one("main")
        or soup.body
        or soup
    )

    images = _all_img_srcs(content, document_base_url)

    return {
        "images": images,
        "description": _clean_text(content),
    }


async def parse_about_page_with_ai(
    html: str,
    base_url: str,
    openai_client: Optional[AsyncOpenAI],
) -> Dict:
    about_data = parse_about_page(html, base_url)
    text_content = _html_to_text(html, preserve_lines=True)
    if not text_content or openai_client is None:
        return about_data

    prompt = f"""
Extract only the company/about-us description from this page text by copying the original text exactly.

Rules:
- Return only valid JSON with exactly this shape: {{"description": string|null}}
- Exclude navigation, menus, copyright text, contact details, tags, buttons, and unrelated page chrome.
- Copy the description text verbatim from the page text. Do not summarize, rewrite, paraphrase, translate, or change wording.
- Keep original capitalization, punctuation, spelling, numbers, and sentence order.
- Preserve paragraph boundaries with newline characters when the source text has separate paragraphs.
- If no about-us description is available, return null.

Page URL: {base_url}

Page text:
{_truncate_for_ai(text_content)}
"""
    try:
        result = await _extract_json_with_ai(
            openai_client,
            system_message="You extract concise company profile descriptions from web page text.",
            user_prompt=prompt,
            max_tokens=700,
        )
        description = result.get("description")
        if isinstance(description, str) and description.strip():
            about_data["description"] = _clean_ai_verbatim_text(description)
        elif description is None:
            about_data["description"] = None
    except Exception:
        pass

    return about_data


def parse_contact_page(html: str, base_url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    contacts = _parse_contacts_boxes(soup)
    if not contacts:
        contacts = _parse_contact_tables(soup)
        contacts.extend(_parse_contact_blocks(soup))

    deduped = []
    seen = set()
    for contact in contacts:
        cleaned = _clean_contact(contact)
        if not cleaned:
            continue
        identity = json.dumps(cleaned, sort_keys=True)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(cleaned)

    return deduped


async def parse_contact_page_with_ai(
    html: str,
    base_url: str,
    openai_client: Optional[AsyncOpenAI],
) -> List[Dict]:
    text_content = _html_to_text(html, preserve_lines=True)
    if not text_content:
        return []

    if openai_client is None:
        return [_complete_contact_fields(contact) for contact in parse_contact_page(html, base_url)]

    prompt = f"""
Extract contact information for every region, office, location, or branch from this contact page.

Return only valid JSON with exactly this shape:
{{
  "regions": [
    {{
      "name": string|null,
      "address": string|null,
      "city": string|null,
      "post_code": string|null,
      "state": string|null,
      "country": string|null,
      "telephone": string|null,
      "phone": string|null,
      "fax": string|null,
      "mail": string|null,
      "contact_person": {{
        "name": string|null,
        "email": string|null,
        "phone": string|null,
        "telephone": string|null,
        "fax": string|null
      }}|null
    }}
  ]
}}

Rules:
- Include all regions/offices/locations present on the page.
- Every region object must include all fields above.
- Use null for fields that are missing or cannot be confidently identified.
- Put email addresses in "mail".
- Put landline labels such as Tel or Telephone in "telephone"; mobile/cell/general Phone in "phone".
- If a region has a "Contacts:" section or named contact person, put that person's data in "contact_person".
- For contact_person, use "email" for the person's email address.
- If no contact person exists for a region, set "contact_person" to null.
- Do not invent values.

Page URL: {base_url}

Page text:
{_truncate_for_ai(text_content)}
"""
    try:
        result = await _extract_json_with_ai(
            openai_client,
            system_message="You extract structured contact data from web page text and return strict JSON.",
            user_prompt=prompt,
            max_tokens=1800,
        )
        regions = result.get("regions", [])
        if isinstance(regions, list):
            cleaned_regions = [
                _complete_contact_fields(region)
                for region in regions
                if isinstance(region, dict) and any(region.get(key) for key in CONTACT_KEYS)
            ]
            return cleaned_regions
    except Exception:
        pass

    return [_complete_contact_fields(contact) for contact in parse_contact_page(html, base_url)]


def _find_middle_content(soup: BeautifulSoup) -> Optional[Tag]:
    return soup.find(id="middle 2") or soup.find(id="middle2") or soup.select_one("#middle")


def _parse_tags(soup: BeautifulSoup) -> List[str]:
    tag_containers = soup.select(".tags, [class*=tag], [id*=tag], a[rel~=tag]")
    if not tag_containers:
        return []

    tags = []
    for tags_container in tag_containers:
        nodes = []
        if tags_container.name in {"a", "span", "li"}:
            nodes.append(tags_container)
        nodes.extend(tags_container.select("a, span, li"))

        for node in nodes:
            tag = _clean_text(node) or _tag_from_href(_attr(node, "href"))
            if tag and tag.lower() != "tags":
                tags.append(tag)

        if not tags:
            container_text = _clean_text(tags_container)
            if container_text:
                pieces = re.split(r"[,|;/\n]+", container_text)
                tags.extend(piece.strip() for piece in pieces if piece.strip().lower() != "tags")

    return _dedupe_strings(tags)


def _parse_sections(soup: BeautifulSoup, base_url: str) -> List[Dict]:
    sections = []
    for block in soup.select(".sectionBlock, .section-block"):
        title_link = block.select_one(".tlt a")
        title_node = title_link or block.select_one(".tlt")
        image_src = _first_img_src(block)
        url = (
            _attr(title_link, "href")
            or _attr(block.select_one(".button a"), "href")
            or _attr(block.select_one("a[href]"), "href")
        )
        title = _clean_text(title_node)

        if not (title or image_src or url):
            continue

        sections.append(
            {
                "title": title,
                "image": _absolute_url(image_src, base_url),
                "url": _absolute_url(url, base_url),
            }
        )

    deduped = []
    seen = set()
    for section in sections:
        identity = (section.get("title"), section.get("url"), section.get("image"))
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(section)
    return deduped


def _parse_contacts_boxes(soup: BeautifulSoup) -> List[Dict]:
    contacts = []
    for box in soup.select(".contacts-box"):
        box_copy = BeautifulSoup(str(box), "html.parser")
        copied_box = box_copy.select_one(".contacts-box") or box_copy
        contact_person_node = copied_box.select_one(".locationcontact")
        contact_person = _parse_contact_person_node(contact_person_node) if contact_person_node else None

        for node in copied_box.select(".locationcontact"):
            node.decompose()

        text = _clean_text(copied_box, separator="\n") or ""
        contact = _parse_contact_text(text)
        heading = copied_box.find("strong")
        heading_text = _clean_text(heading)
        if heading_text and heading_text.lower().strip(":") != "contacts" and not heading_text.strip().endswith(":"):
            contact["name"] = heading_text
        if contact_person:
            contact["contact_person"] = contact_person
        if _has_contact_data(contact) or contact.get("name"):
            contacts.append(contact)
    return contacts


def _parse_contact_tables(soup: BeautifulSoup) -> List[Dict]:
    contacts = []
    for table in soup.select("table"):
        contact = {}
        for row in table.select("tr"):
            cells = [_clean_text(cell) for cell in row.find_all(["th", "td"], recursive=False)]
            cells = [cell for cell in cells if cell]
            if len(cells) < 2:
                continue
            key = _normalize_contact_label(cells[0])
            if key:
                contact[key] = cells[1]
        if _has_contact_data(contact):
            contacts.append(contact)
    return contacts


def _parse_contact_blocks(soup: BeautifulSoup) -> List[Dict]:
    candidates = _contact_block_candidates(soup)
    contacts = []
    for block in candidates:
        text = _clean_text(block, separator="\n")
        if not _has_contact_signal(text):
            continue
        contact = _parse_contact_text(text)
        mailto = _first_mailto(block)
        if mailto and not contact.get("mail"):
            contact["mail"] = mailto
        if _has_contact_data(contact):
            contacts.append(contact)
    return contacts


def _contact_block_candidates(soup: BeautifulSoup) -> List[Tag]:
    matched = []
    for node in soup.find_all(True):
        class_id = " ".join(
            str(value)
            for value in [
                node.get("id", ""),
                " ".join(node.get("class", [])) if isinstance(node.get("class"), list) else node.get("class", ""),
            ]
        ).lower()
        text = _clean_text(node)
        if (
            re.search(r"(contact|address|location|office|branch|region)", class_id)
            and _has_contact_signal(text)
        ):
            matched.append(node)

    if not matched:
        main = _find_middle_content(soup) or soup.select_one("main") or soup.body
        if main:
            matched = [main]

    lowest_level = []
    matched_set = set(matched)
    for node in matched:
        if not any(child in matched_set for child in node.find_all(True)):
            lowest_level.append(node)

    return lowest_level or matched


def _parse_contact_text(text: str) -> Dict:
    lines = [_strip_label_noise(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    lines = _combine_split_contact_label_lines(lines)
    contact = {}
    remaining = []

    for line in lines:
        if line.lower().strip(":") in {"email", "e-mail", "mail", "contact", "contacts", "contact us"}:
            continue

        extracted = _extract_labeled_contact_value(line)
        if extracted:
            key, value = extracted
            if value and not contact.get(key):
                contact[key] = value
            continue

        if line.strip().endswith(":"):
            continue

        email = _extract_email(line)
        if email and not contact.get("mail"):
            contact["mail"] = email
            line = line.replace(email, "").strip(" :-")
            if not line:
                continue

        remaining.append(line)

    if not contact.get("name"):
        heading = _first_non_address_line(remaining)
        if heading:
            contact["name"] = heading
            remaining = [line for line in remaining if line != heading]

    _parse_address_lines(contact, remaining)
    return contact


def _parse_contact_person_node(node: Optional[Tag]) -> Optional[Dict]:
    if not node:
        return None
    text = _clean_text(node, separator="\n") or ""
    lines = [_strip_label_noise(line) for line in text.splitlines()]
    lines = [line for line in lines if line and line.lower().strip(":") not in {"contacts", "contact"}]
    lines = _combine_split_contact_label_lines(lines)
    contact_person = _parse_contact_person_lines(lines)
    return _complete_contact_person_fields(contact_person) if any(contact_person.values()) else None


def _parse_contact_person_lines(lines: List[str]) -> Dict:
    contact_person = {}
    remaining = []
    skip_next = False

    for index, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue

        embedded_label = re.match(r"^(.+?)\s+(phone|telephone|tel|fax)\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        if embedded_label:
            name = embedded_label.group(1).strip()
            label = embedded_label.group(2).lower()
            value = embedded_label.group(3).strip()
            if not value and index + 1 < len(lines):
                value = lines[index + 1]
                skip_next = True
            if name and not contact_person.get("name"):
                contact_person["name"] = name
            if value:
                if label == "fax":
                    contact_person["fax"] = value
                elif label in {"telephone", "tel"}:
                    contact_person["telephone"] = value
                else:
                    contact_person["phone"] = value
            continue

        label = line.lower().strip(":")
        next_line = lines[index + 1] if index + 1 < len(lines) else ""

        if label in {"phone", "mobile", "cell"} and next_line:
            contact_person["phone"] = next_line
            skip_next = True
            continue
        if label in {"telephone", "tel"} and next_line:
            contact_person["telephone"] = next_line
            skip_next = True
            continue
        if label == "fax" and next_line:
            contact_person["fax"] = next_line
            skip_next = True
            continue

        extracted = _extract_labeled_contact_value(line)
        if extracted:
            key, value = extracted
            if key == "mail":
                contact_person["email"] = value
            elif key in {"phone", "telephone", "fax"}:
                contact_person[key] = value
            elif key == "name":
                contact_person["name"] = value
            continue

        email = _extract_email(line)
        if email:
            contact_person["email"] = email
            line = line.replace(email, "").strip(" :-")
            if not line:
                continue

        if not _looks_like_phone_number(line):
            remaining.append(line)

    if not contact_person.get("name") and remaining:
        contact_person["name"] = remaining[0]

    return contact_person


def _extract_labeled_contact_value(line: str) -> Optional[tuple]:
    patterns = [
        ("telephone", r"^(telephone|tel\.?)\s*[:\-]?\s*(.+)$"),
        ("phone", r"^(phone|mobile|cell)\s*[:\-]?\s*(.+)$"),
        ("fax", r"^(fax)\s*[:\-]?\s*(.+)$"),
        ("mail", r"^(mail|email|e-mail)\s*[:\-]?\s*(.+)$"),
        ("address", r"^(address)\s*[:\-]?\s*(.+)$"),
        ("city", r"^(city)\s*[:\-]?\s*(.+)$"),
        ("post_code", r"^(post\s*code|postal\s*code|zip|zipcode|zip\s*code)\s*[:\-]?\s*(.+)$"),
        ("state", r"^(state|province)\s*[:\-]?\s*(.+)$"),
        ("country", r"^(country)\s*[:\-]?\s*(.+)$"),
        ("name", r"^(name|region|office|branch)\s*[:\-]?\s*(.+)$"),
    ]
    for key, pattern in patterns:
        match = re.match(pattern, line, flags=re.IGNORECASE)
        if match:
            return key, match.group(2).strip()
    return None


def _combine_split_contact_label_lines(lines: List[str]) -> List[str]:
    combined = []
    skip_next = False
    labels = {"phone", "telephone", "tel", "fax", "email", "e-mail", "mail"}
    for index, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        label = line.lower().strip(":")
        if label in labels and index + 1 < len(lines):
            combined.append(f"{line} {lines[index + 1]}")
            skip_next = True
            continue
        combined.append(line)
    return combined


def _parse_address_lines(contact: Dict, lines: List[str]) -> None:
    address_lines = []
    for line in lines:
        if not contact.get("country") and line.lower() in COUNTRY_NAMES:
            contact["country"] = line
            continue

        if not contact.get("post_code") and _is_canadian_post_code(line):
            contact["post_code"] = line.upper()
            continue

        city_state_country = _parse_city_state_country(line)
        if city_state_country:
            contact.update({k: v for k, v in city_state_country.items() if v and not contact.get(k)})
            continue

        city_state_post = _parse_city_state_post_code(line)
        if city_state_post:
            contact.update({k: v for k, v in city_state_post.items() if v and not contact.get(k)})
            continue

        if line != contact.get("name"):
            address_lines.append(line)

    if address_lines and not contact.get("address"):
        contact["address"] = ", ".join(address_lines)


def _parse_city_state_post_code(line: str) -> Optional[Dict]:
    canadian = re.match(
        r"^(.+?)\s+([A-Z]{2})\s+([A-Z]\d[A-Z][ -]?\d[A-Z]\d)$",
        line.strip(),
        flags=re.IGNORECASE,
    )
    if canadian:
        return {
            "city": canadian.group(1).strip(", "),
            "state": canadian.group(2).upper(),
            "post_code": canadian.group(3).upper(),
        }

    us = re.match(r"^(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$", line.strip(), flags=re.IGNORECASE)
    if us:
        return {
            "city": us.group(1).strip(),
            "state": us.group(2).upper(),
            "post_code": us.group(3),
        }

    return None


def _parse_city_state_country(line: str) -> Optional[Dict]:
    parts = [part.strip() for part in line.split(",") if part.strip()]
    if len(parts) != 3:
        return None
    city, state, country = parts
    if not city or not state or not country:
        return None
    return {
        "city": city,
        "state": state,
        "country": country,
    }


def _is_canadian_post_code(line: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]\d[A-Z][ -]?\d[A-Z]\d", line.strip(), flags=re.IGNORECASE))


def _normalize_contact_label(label: str) -> Optional[str]:
    normalized = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    aliases = {
        "postal_code": "post_code",
        "post_code": "post_code",
        "zip": "post_code",
        "zip_code": "post_code",
        "e_mail": "mail",
        "email": "mail",
        "mail": "mail",
        "tel": "telephone",
        "telephone": "telephone",
        "phone": "phone",
        "mobile": "phone",
        "cell": "phone",
        "province": "state",
        "state": "state",
    }
    return aliases.get(normalized, normalized if normalized in CONTACT_KEYS else None)


def _clean_contact(contact: Dict) -> Dict:
    cleaned = {}
    for key in CONTACT_KEYS:
        value = contact.get(key)
        if isinstance(value, str):
            value = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip(" ,;:-")
        if value:
            cleaned[key] = value
    contact_person = contact.get("contact_person")
    if isinstance(contact_person, dict):
        cleaned["contact_person"] = _complete_contact_person_fields(contact_person)
    return cleaned


def _complete_contact_fields(contact: Dict) -> Dict:
    completed = {}
    for key in CONTACT_FIELD_NAMES:
        if key == "contact_person":
            contact_person = contact.get("contact_person")
            completed[key] = (
                _complete_contact_person_fields(contact_person)
                if isinstance(contact_person, dict) and any(contact_person.get(field) for field in CONTACT_PERSON_FIELD_NAMES)
                else None
            )
            continue

        value = contact.get(key)
        if isinstance(value, str):
            value = _normalize_space(value).strip(" ,;:-") or None
        elif value is not None:
            value = str(value).strip() or None
        completed[key] = value
    return completed


def _complete_contact_person_fields(contact_person: Dict) -> Dict:
    completed = {}
    for key in CONTACT_PERSON_FIELD_NAMES:
        value = contact_person.get(key)
        if isinstance(value, str):
            value = _normalize_space(value).strip(" ,;:-") or None
        elif value is not None:
            value = str(value).strip() or None
        completed[key] = value
    return completed


def _has_contact_data(contact: Dict) -> bool:
    return any(contact.get(key) for key in ("telephone", "phone", "fax", "mail", "address", "city", "contact_person"))


def _has_contact_signal(text: str) -> bool:
    return bool(
        re.search(
            r"(@|mailto:|\btelephone\b|\btel\.?\b|\bphone\b|\bfax\b|\bemail\b|\baddress\b|\bpostal\b|\bzip\b)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _first_non_address_line(lines: List[str]) -> Optional[str]:
    for line in lines:
        if _extract_email(line) or _parse_city_state_post_code(line):
            continue
        if line.lower() in COUNTRY_NAMES:
            continue
        if re.search(r"\d", line) and re.search(r"\b(st|street|road|rd|drive|dr|ave|avenue|blvd|suite)\b", line, re.I):
            continue
        return line
    return None


def _strip_label_noise(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _extract_email(text: str) -> Optional[str]:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else None


def _looks_like_phone_number(text: str) -> bool:
    return bool(re.fullmatch(r"[\d\s().+\-xXextEXT]+", text.strip())) and bool(re.search(r"\d", text))


def _first_mailto(node: Tag) -> Optional[str]:
    link = node.select_one('a[href^="mailto:"]')
    if not link:
        return None
    href = _attr(link, "href")
    if not href:
        return None
    return href.replace("mailto:", "").split("?")[0].strip()


def _first_img_src(node: Optional[Tag]) -> Optional[str]:
    if not node:
        return None
    img = node.select_one("img[src]")
    return _attr(img, "src")


def _all_img_srcs(node: Optional[Tag], base_url: str) -> List[str]:
    if not node:
        return []
    urls = []
    for img in node.select("img[src]"):
        absolute_url = _absolute_url(_attr(img, "src"), base_url)
        if absolute_url:
            urls.append(absolute_url)
    return _dedupe_strings(urls)


def _attr(node: Optional[Tag], attr_name: str) -> Optional[str]:
    if not node:
        return None
    value = node.get(attr_name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _absolute_url(url: Optional[str], base_url: str) -> Optional[str]:
    if not url:
        return None
    return urljoin(base_url, url)


def _document_base_url(soup: BeautifulSoup, fallback_url: str) -> str:
    base_href = _attr(soup.select_one("base[href]"), "href")
    return urljoin(fallback_url, base_href) if base_href else fallback_url


def _clean_text(node: Optional[Tag], separator: str = " ") -> Optional[str]:
    if not node:
        return None
    text = node.get_text(separator, strip=True) if isinstance(node, Tag) else str(node)
    text = text.replace("\xa0", " ")
    if separator == "\n":
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
    else:
        text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _dedupe_strings(values: List[str]) -> List[str]:
    deduped = []
    seen = set()
    for value in values:
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped


def _tag_from_href(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    path = urlparse(href).path
    if not path:
        return None
    tag = unquote(path.rstrip("/").split("/")[-1]).strip()
    return tag or None


def _build_openai_client() -> Optional[AsyncOpenAI]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return AsyncOpenAI(api_key=api_key)


async def _extract_json_with_ai(
    openai_client: AsyncOpenAI,
    system_message: str,
    user_prompt: str,
    max_tokens: int,
) -> Dict:
    response = await openai_client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    content = response.choices[0].message.content or ""
    return json.loads(_strip_json_code_fence(content))


def _strip_json_code_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _html_to_text(html: str, preserve_lines: bool = False) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    text = soup.get_text("\n", strip=True)
    if preserve_lines:
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line.replace("\xa0", " ")).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
    return _normalize_space(text)


def _truncate_for_ai(text: str) -> str:
    max_chars = int(os.getenv("COMPANY_AI_EXTRACTION_MAX_CHARS", os.getenv("AI_EXTRACTION_MAX_CHARS", "12000")))
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _clean_ai_verbatim_text(text: str) -> str:
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line.replace("\xa0", " ")).strip() for line in text.splitlines()]
    cleaned_lines = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False
    return "\n".join(cleaned_lines).strip()
