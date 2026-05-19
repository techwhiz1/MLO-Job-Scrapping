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
    def __init__(self, filter_location: bool = False):
        # Set OpenAI API key
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # OpenAI client for AI extraction
        self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        
        # Create debug directory if it doesn't exist
        self.debug_dir = "debug_html"
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
        
        # Track scraped URLs to prevent duplicates
        self.scraped_urls = set()
        self.scraped_jobs = []  # Store successfully scraped jobs
        
        # Location filtering
        self.filter_location = filter_location

    def _selenium_http_timeout_seconds(self) -> int:
        """HTTP read timeout for chromedriver (large page_source needs more than default 120s)."""
        return int(os.getenv("SELENIUM_HTTP_READ_TIMEOUT", "300"))

    def _selenium_page_load_timeout_seconds(self) -> int:
        return int(os.getenv("SELENIUM_PAGE_LOAD_TIMEOUT", "45"))

    def _selenium_script_timeout_seconds(self) -> int:
        return int(os.getenv("SELENIUM_SCRIPT_TIMEOUT", "120"))

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
        try:
            print(f"Loading listing page + iframes (single session): {url}")
            driver = self._setup_selenium_driver()
            self._selenium_navigate(driver, url)

            print(f"Waiting {delay} seconds for JavaScript to render...")
            time.sleep(delay)

            if wait_for_elements:
                combined_selector = ", ".join(wait_for_elements)
                try:
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, combined_selector))
                    )
                    print(f"✅ Found page-ready element(s): {combined_selector}")
                except TimeoutException:
                    print("⚠️ Quick wait timeout for job selectors, continue with current DOM")

            print("Scrolling progressively to load JS/lazy job cards (main document)...")
            previous_height = driver.execute_script("return document.body.scrollHeight")
            stable_rounds = 0
            max_rounds = 6
            for round_index in range(max_rounds):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.0)
                for h in self._selenium_collect_careers_jobs_detail_hrefs(driver):
                    if h not in careers_seen:
                        careers_seen.add(h)
                        careers_job_hrefs.append(h)
                current_height = driver.execute_script("return document.body.scrollHeight")
                if current_height == previous_height:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                previous_height = current_height
                if stable_rounds >= 2:
                    break
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            for h in self._selenium_collect_careers_jobs_detail_hrefs(driver):
                if h not in careers_seen:
                    careers_seen.add(h)
                    careers_job_hrefs.append(h)

            # SilkRoad embed: iframe starts as loading.html; snippet swaps src async — often still
            # loading when we snapshot. Resolve real listing URL from cxembeddedroot / data-* and set src.
            driver.switch_to.default_content()
            resolved_listing = self._resolve_silkroad_careers_listing_url(url, driver)
            if resolved_listing:
                print(f"📎 Resolved SilkRoad listing URL: {resolved_listing[:140]}...")
                if not self._wait_silkroad_iframe_navigated_from_loading(driver, timeout=25.0):
                    self._force_silkroad_iframe_src(driver, resolved_listing)
                    time.sleep(2)
                self._wait_silkroad_iframe_navigated_from_loading(driver, timeout=90.0)
                time.sleep(4)
            else:
                self._wait_silkroad_iframe_navigated_from_loading(driver, timeout=60.0)

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
                    time.sleep(4)
                    driver.switch_to.default_content()
                    el = driver.find_elements(By.ID, "silkroadJobs_cx_container")
                    el = el[0] if el else iframes_now[idx]
                    src = (el.get_attribute("src") or "").strip()
                    iframe_base = urljoin(url, src) if src else url
                try:
                    driver.switch_to.frame(el)
                    time.sleep(max(2, delay))
                    try:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, iframe_wait_selector))
                        )
                        print(f"✅ Iframe {idx} ready ({iframe_base[:80]}...)")
                    except TimeoutException:
                        print(f"⚠️ Iframe {idx}: no job-like links quickly; still capturing DOM")

                    # Scroll iframe and collect /Careers/jobs/{id} hrefs each step (virtualized lists)
                    stable = 0
                    prev = driver.execute_script(
                        "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
                    )
                    for r in range(iframe_scroll_rounds):
                        driver.execute_script(
                            "window.scrollTo(0, Math.max(document.body.scrollHeight, "
                            "document.documentElement.scrollHeight));"
                        )
                        time.sleep(0.65)
                        for h in self._selenium_collect_careers_jobs_detail_hrefs(driver):
                            if h not in careers_seen:
                                careers_seen.add(h)
                                careers_job_hrefs.append(h)
                        cur = driver.execute_script(
                            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
                        )
                        if cur == prev:
                            stable += 1
                            if stable >= 2 and r > 1:
                                break
                        else:
                            stable = 0
                        prev = cur
                    for h in self._selenium_collect_careers_jobs_detail_hrefs(driver):
                        if h not in careers_seen:
                            careers_seen.add(h)
                            careers_job_hrefs.append(h)

                    if "silkroad" in iframe_base.lower():
                        print(f"📄 SilkRoad iframe: paginating to collect all /Careers/jobs/{{id}} links...")
                        self._selenium_paginate_and_collect_careers_jobs(
                            driver, careers_seen, careers_job_hrefs
                        )

                    inner_html = driver.page_source
                    chunks.append((iframe_base, inner_html))
                    print(f"✅ Iframe {idx} inner HTML: {len(inner_html)} characters")

                    # One level of nested iframes (some ATS embed twice)
                    nested = driver.find_elements(By.TAG_NAME, "iframe")
                    for j in range(len(nested)):
                        try:
                            in_list = driver.find_elements(By.TAG_NAME, "iframe")
                            if j >= len(in_list):
                                break
                            nel = in_list[j]
                            nsrc = (nel.get_attribute("src") or "").strip()
                            nbase = urljoin(iframe_base, nsrc) if nsrc else iframe_base
                            driver.switch_to.frame(nel)
                            time.sleep(2)
                            try:
                                WebDriverWait(driver, 12).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, iframe_wait_selector))
                                )
                            except TimeoutException:
                                pass
                            stable_n = 0
                            prev_n = driver.execute_script(
                                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
                            )
                            for r in range(8):
                                driver.execute_script(
                                    "window.scrollTo(0, Math.max(document.body.scrollHeight, "
                                    "document.documentElement.scrollHeight));"
                                )
                                time.sleep(0.6)
                                for h in self._selenium_collect_careers_jobs_detail_hrefs(driver):
                                    if h not in careers_seen:
                                        careers_seen.add(h)
                                        careers_job_hrefs.append(h)
                                cur_n = driver.execute_script(
                                    "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
                                )
                                if cur_n == prev_n:
                                    stable_n += 1
                                    if stable_n >= 2 and r > 1:
                                        break
                                else:
                                    stable_n = 0
                                prev_n = cur_n
                            for h in self._selenium_collect_careers_jobs_detail_hrefs(driver):
                                if h not in careers_seen:
                                    careers_seen.add(h)
                                    careers_job_hrefs.append(h)

                            if "silkroad" in nbase.lower():
                                print(f"📄 Nested SilkRoad iframe: paginating...")
                                self._selenium_paginate_and_collect_careers_jobs(
                                    driver, careers_seen, careers_job_hrefs
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
        
    async def scrape_jobs(self, url: str, max_jobs: Optional[int] = None) -> List[Dict]:
        """Main function to scrape all jobs from a given URL with pagination support.
        If max_jobs is set, scraping stops after that many jobs have been successfully scraped."""
        # Reset scraping state for new session
        self.reset_scraping_state()
        
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
            
            # Single Selenium session: main + iframe HTML + live /Careers/jobs/{id} href collection
            html_chunks, dom_careers_job_urls = self._get_listing_html_chunks(url, wait_for_elements, delay=2)
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
                chunk_links = await self._extract_job_links(chunk_html, chunk_base)
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
            async with AsyncWebCrawler(verbose=True) as crawler:
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
                        
                        print(f"🔄 Scraping job {i}/{len(unique_job_links)}: {job_url}")
                        job_data = await self._scrape_individual_job_with_crawl4ai(job_url)
                        
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
    
    async def _extract_job_links(self, html: str, base_url: str) -> List[str]:
        """Extract job links from the HTML content, ignoring headers and footers"""
        soup = BeautifulSoup(html, 'html.parser')
        job_links = []
        
        # Only remove head and footer elements - keep everything else
        elements_to_remove = [
            'head', 'footer'
        ]
        
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
        
        print(f"Removed {removed_count} <head>/<footer> elements")
        
        # Use the entire remaining document (no main content filtering)
        main_content = soup
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
        
        print(f"Extracting job links from cleaned document...")
        
        # DEBUG: Show a sample of the remaining HTML to verify structure
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
            try:
                # Search within the cleaned document
                links = main_content.select(selector)
                print(f"Selector '{selector}' found {len(links)} links")
                
                for link in links:
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
                        print(f"Skipping link inside header/footer: {link.get('href', '')}")
                        continue
                    
                    href = link.get('href')
                    if href:
                        full_url = urljoin(base_url, href)
                        # Simplified validation - just check if it's a job URL
                        if self._is_job_url(full_url):
                            job_links.append(full_url)
                            print(f"Added job link: {full_url}")
            except Exception as e:
                print(f"Error with selector '{selector}': {str(e)}")
                continue

        # Regex pass: picks up URLs in script/JSON or non-standard attributes (common in SPAs / SilkRoad)
        for ru in self._extract_detail_job_urls_regex(html, base_url):
            if re.search(r"/(?:[Cc]areers/)?jobs/\d+", ru) or re.search(r"OpportunityDetail.*opportunityId=", ru, re.IGNORECASE):
                job_links.append(ru)
                print(f"Added job link (regex): {ru}")
        
        unique_links = list(set(job_links))  # Remove duplicates
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
        try:
            # Fix encoding artifacts: "Â" before non-breaking spaces (UTF-8 double-encoding)
            html_content = html_content.replace("\u00c2\u00a0", "\u00a0")  # Â + nbsp → nbsp
            html_content = html_content.replace("\u00c2 ", " ")            # Â + space → space
            # Standalone Â that shouldn't be there
            html_content = re.sub(r"\u00c2(?=\s|<|&)", "", html_content)

            soup = BeautifulSoup(html_content, "html.parser")
            # Remove branding container(s), e.g. SilkRoad / ATS "asbranding"
            for el in soup.find_all(True):
                eid = (el.get("id") or "").strip()
                if eid.lower() == "asbranding":
                    el.decompose()
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
            return str(soup)
        except Exception as e:
            logger.warning(f"html_content post-process skipped: {e}")
            return html_content

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
                
                # Wait for page to load
                time.sleep(2)
                
                # Scroll to ensure all elements are rendered
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
                    
                    // Remove elements with "search" or "apply-button" in id or classname
                    function shouldRemoveElement(element) {
                        const id = element.getAttribute('id') || '';
                        const className = element.getAttribute('class') || '';
                        const idLower = id.toLowerCase();
                        const classLower = className.toLowerCase();
                        return idLower.includes('search') || idLower.includes('apply-button') ||
                               classLower.includes('search') || classLower.includes('apply-button');
                    }
                    
                    // Remove matching elements
                    const allElements = document.querySelectorAll('*');
                    const elementsToRemove = [];
                    allElements.forEach(el => {
                        if (hasHeaderFooter(el) || shouldRemoveElement(el)) {
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
            
            # Remove elements with "search" or "apply-button" in id or classname
            for element in soup.find_all(True):
                element_id = element.get('id', '') or ''
                element_class = element.get('class', [])
                if isinstance(element_class, list):
                    element_class = ' '.join(element_class)
                else:
                    element_class = str(element_class) or ''
                
                id_lower = element_id.lower()
                class_lower = element_class.lower()
                
                if 'search' in id_lower or 'search' in class_lower or \
                   'apply-button' in id_lower or 'apply-button' in class_lower:
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
    
    async def _scrape_individual_job_with_crawl4ai(self, job_url: str) -> Optional[Dict]:
        """Scrape individual job details using Crawl4AI and OpenAI for extraction"""
        try:
            logger.info(f"Scraping job with Crawl4AI: {job_url}")
            
            # Use Crawl4AI to get the HTML with delay
            async with AsyncWebCrawler(verbose=True) as crawler:
                result = await crawler.arun(
                    url=job_url,
                    delay_before_return_html=2,  # 2 second delay
                    timeout=30000,
                    page_timeout=60000
                )
            
            if not result.success:
                logger.error(f"Failed to crawl job page: {job_url}")
                return None
            
            # Save HTML for debugging
            if hasattr(result, 'html') and result.html:
                self._save_html_debug(result.html, job_url, "individual_job")
            
            # Extract HTML content with inlined styles
            html_content = await self._extract_html_content_with_styles(result.html, job_url)
            
            # Use OpenAI to extract structured data from the HTML
            job_data = await self._extract_job_data_with_ai(result.html, job_url)
            
            # Add HTML content to job data
            if html_content:
                job_data["html_content"] = html_content
            
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
        
        # Get text content and limit length
        text_content = soup.get_text()
        # Limit to ~4000 characters to stay within token limits
        if len(text_content) > 4000:
            text_content = text_content[:4000] + "..."
        
        prompt = f"""
        Extract job information from the following job posting content. Return the data as a JSON object with these exact fields:

        - employer: Company/organization name
        - job_title: Job position title
        - job_id: Job ID or reference number if available
        - job_description: Brief job description/summary
        - location: Job location (city, state, country)
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

        Job URL: {job_url}
        
        Job Content:
        {text_content}
        
        Return only valid JSON. If a field is not found, use null as the value.
        """
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a job data extraction assistant. Extract job information and return it as valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
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
                "source_url": job_url
            }
