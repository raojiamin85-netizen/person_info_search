import requests
import time
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from config import SEARCH_URLS, DEFAULT_HEADERS, SEARCH_TIMEOUT, REQUEST_DELAY, MAX_SEARCH_RESULTS
from utils import clean_text, logger

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]

class WebSearch:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.use_selenium = False
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            self.use_selenium = True
            logger.info("Selenium 已加载，将使用浏览器模式")
        except ImportError:
            logger.warning("Selenium 未安装，将使用简单HTTP请求模式")
    
    def _random_headers(self):
        headers = DEFAULT_HEADERS.copy()
        headers['User-Agent'] = random.choice(USER_AGENTS)
        return headers
    
    def _request_with_retry(self, url, params=None, max_retries=3):
        for attempt in range(max_retries):
            try:
                self.session.headers.update(self._random_headers())
                response = self.session.get(url, params=params, timeout=SEARCH_TIMEOUT)
                response.raise_for_status()
                
                if '安全验证' in response.text or '百度安全验证' in response.text:
                    logger.warning(f"请求被安全验证拦截，尝试第 {attempt + 1} 次")
                    if attempt < max_retries - 1:
                        time.sleep(5)
                        continue
                    return None
                
                return response
            except requests.exceptions.RequestException as e:
                logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        return None
    
    def _search_with_selenium(self, url, query, num_results=MAX_SEARCH_RESULTS):
        results = []
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.keys import Keys
            
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--lang=zh-CN')
            
            driver = webdriver.Chrome(options=chrome_options)
            wait = WebDriverWait(driver, 10)
            
            try:
                if 'baidu' in url:
                    driver.get('https://www.baidu.com/s?wd=' + query)
                    source_name = '百度搜索'
                elif 'bing' in url:
                    driver.get('https://www.bing.com/search?q=' + query)
                    source_name = '必应搜索'
                else:
                    driver.get('https://www.sogou.com/web?query=' + query)
                    source_name = '搜狗搜索'
                
                time.sleep(random.uniform(3, 5))
                
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'lxml')
                
                if 'baidu' in url:
                    items = soup.find_all('div', class_='result') or soup.find_all('div', class_='c-container')
                elif 'bing' in url:
                    items = soup.find_all('li', class_='b_algo') or soup.find_all('div', class_='b_algo')
                else:
                    items = soup.find_all('div', class_='vrwrap') or soup.find_all('div', class_='result')
                
                for item in items[:num_results]:
                    title_tag = item.find('h3') or item.find('h2')
                    link_tag = item.find('a')
                    summary_tag = item.find('p', class_='c-abstract') or item.find('p')
                    
                    if title_tag and link_tag:
                        results.append({
                            'title': clean_text(title_tag.get_text()),
                            'url': link_tag.get('href'),
                            'summary': clean_text(summary_tag.get_text()) if summary_tag else '',
                            'source': source_name,
                            'type': 'search'
                        })
                
                logger.info(f"Selenium {source_name} 获取到 {len(results)} 条结果")
            finally:
                driver.quit()
                
        except Exception as e:
            logger.error(f"Selenium搜索失败: {e}")
        
        return results
    
    def search_baidu(self, query, num_results=MAX_SEARCH_RESULTS):
        if self.use_selenium:
            return self._search_with_selenium('https://www.baidu.com', query, num_results)
        
        results = []
        try:
            url = 'https://www.baidu.com/s'
            params = {'wd': query, 'pn': 0, 'rn': num_results}
            response = self._request_with_retry(url, params)
            
            if not response:
                logger.warning("百度搜索被安全验证拦截")
                return results
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            items = soup.find_all('div', class_='result')
            if not items:
                items = soup.find_all('div', class_='c-container')
            
            for item in items[:num_results]:
                title_tag = item.find('h3') or item.find('h2')
                link_tag = item.find('a')
                summary_tag = item.find('p', class_='c-abstract') or item.find('span', class_='content-right_8Zs40')
                
                if title_tag and link_tag:
                    results.append({
                        'title': clean_text(title_tag.get_text()),
                        'url': link_tag.get('href'),
                        'summary': clean_text(summary_tag.get_text()) if summary_tag else '',
                        'source': '百度搜索',
                        'type': 'search'
                    })
                    
            logger.info(f"百度搜索获取到 {len(results)} 条结果")
        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
        
        return results
    
    def search_bing(self, query, num_results=MAX_SEARCH_RESULTS):
        if self.use_selenium:
            return self._search_with_selenium('https://www.bing.com', query, num_results)
        
        results = []
        try:
            url = 'https://www.bing.com/search'
            params = {'q': query, 'count': num_results}
            response = self._request_with_retry(url, params)
            
            if not response:
                logger.warning("必应搜索被安全验证拦截")
                return results
            
            soup = BeautifulSoup(response.text, 'lxml')
            items = soup.find_all('li', class_='b_algo')
            
            if not items:
                items = soup.find_all('div', class_='b_algo')
            
            for item in items[:num_results]:
                title_tag = item.find('h2') or item.find('h3')
                link_tag = item.find('a')
                summary_tag = item.find('p')
                
                if title_tag and link_tag:
                    results.append({
                        'title': clean_text(title_tag.get_text()),
                        'url': link_tag.get('href'),
                        'summary': clean_text(summary_tag.get_text()) if summary_tag else '',
                        'source': '必应搜索',
                        'type': 'search'
                    })
                    
            logger.info(f"必应搜索获取到 {len(results)} 条结果")
        except Exception as e:
            logger.error(f"必应搜索失败: {e}")
        
        return results
    
    def search_sogou(self, query, num_results=MAX_SEARCH_RESULTS):
        if self.use_selenium:
            return self._search_with_selenium('https://www.sogou.com', query, num_results)
        
        results = []
        try:
            url = 'https://www.sogou.com/web'
            params = {'query': query, 'num': num_results}
            response = self._request_with_retry(url, params)
            
            if not response:
                logger.warning("搜狗搜索被安全验证拦截")
                return results
            
            soup = BeautifulSoup(response.text, 'lxml')
            items = soup.find_all('div', class_='vrwrap')
            
            if not items:
                items = soup.find_all('div', class_='result')
            
            for item in items[:num_results]:
                title_tag = item.find('h3') or item.find('h2')
                link_tag = item.find('a')
                summary_tag = item.find('p') or item.find('div', class_='content')
                
                if title_tag and link_tag:
                    results.append({
                        'title': clean_text(title_tag.get_text()),
                        'url': link_tag.get('href'),
                        'summary': clean_text(summary_tag.get_text()) if summary_tag else '',
                        'source': '搜狗搜索',
                        'type': 'search'
                    })
                    
            logger.info(f"搜狗搜索获取到 {len(results)} 条结果")
        except Exception as e:
            logger.error(f"搜狗搜索失败: {e}")
        
        return results
    
    def search_wechat(self, query, num_results=MAX_SEARCH_RESULTS):
        results = []
        try:
            url = 'https://weixin.sogou.com/weixin'
            params = {'type': 2, 'query': query, 'page': 1}
            response = self._request_with_retry(url, params)
            
            if not response:
                logger.warning("微信公众号搜索被安全验证拦截")
                return results
            
            soup = BeautifulSoup(response.text, 'lxml')
            items = soup.find_all('div', class_='news-list')
            
            if not items:
                items = soup.find_all('li', class_='news-item')
            
            for item in items[:num_results]:
                title_tag = item.find('h3') or item.find('h4')
                link_tag = item.find('a')
                summary_tag = item.find('p', class_='txt-info') or item.find('p', class_='description')
                
                if title_tag and link_tag:
                    results.append({
                        'title': clean_text(title_tag.get_text()),
                        'url': link_tag.get('href'),
                        'summary': clean_text(summary_tag.get_text()) if summary_tag else '',
                        'source': '微信公众号',
                        'type': 'wechat'
                    })
                    
            logger.info(f"微信公众号搜索获取到 {len(results)} 条结果")
        except Exception as e:
            logger.error(f"微信公众号搜索失败: {e}")
        
        return results
    
    def _is_relevant(self, title, summary, person_info):
        name = person_info.get('name', '')
        company = person_info.get('company', '')
        position = person_info.get('position', '')
        region = person_info.get('region', '')

        irrelevant_keywords = [
            '动物', '生肖', '属相', '马的习性', '马品种', '马拉松', '歌曲', '歌手', '音乐', '小说',
            '电影', '电视剧', '历史人物', '游戏', '彩票', '壁纸', '头像', '百科', '教程', '下载'
        ]
        
        for keyword in irrelevant_keywords:
            if keyword in title or (summary and keyword in summary):
                return False
        
        if len(title) < 5 or title.isdigit():
            return False
        
        text = f'{title} {summary or ""}'
        if name and name in title:
            return True

        if name and name in text:
            return True

        if company and company in text:
            return True

        if position and position in text:
            return True

        if region and region in text:
            return True

        if name and len(name) <= 2:
            support_terms = ['人物', '履历', '专访', '任职', '任命', '离职', '入职', '创始人', '高管', '董事长']
            if company and company in text:
                return True
            if any(term in text for term in support_terms):
                return True
        
        if summary and name in summary:
            return True

        return False

    def _build_queries(self, person_info):
        name = person_info['name']
        company = person_info.get('company')
        position = person_info.get('position')
        region = person_info.get('region')

        queries = []

        if company:
            queries.append(f'{name} {company} 新闻 报道')
            queries.append(f'{name} {company} 履历')
            queries.append(f'{name} {company} 访谈 专访')
        if position:
            queries.append(f'{name} {position} 报道')
            queries.append(f'{name} {position} 任职 履历')
        if region:
            queries.append(f'{name} {region} 新闻')
            queries.append(f'{name} {region} 采访')

        queries.append(f'{name} 人物 报道')
        queries.append(f'{name} 新闻 采访')
        queries.append(f'{name} 履历 任职')
        queries.append(f'{name} 专访 报道')

        unique_queries = []
        seen = set()
        for query in queries:
            if query not in seen:
                seen.add(query)
                unique_queries.append(query)

        return unique_queries

    def _normalise_item(self, item, source_name):
        title_tag = item.find('h3') or item.find('h2')
        link_tag = item.find('a')
        summary_tag = item.find('p', class_='c-abstract') or item.find('p') or item.find('div', class_='content')

        if not (title_tag and link_tag):
            return None

        title = clean_text(title_tag.get_text())
        summary = clean_text(summary_tag.get_text()) if summary_tag else ''
        if not title:
            return None

        return {
            'title': title,
            'url': link_tag.get('href'),
            'summary': summary,
            'source': source_name,
            'type': 'search'
        }
    
    def search_all(self, person_info):
        queries = self._build_queries(person_info)
        
        logger.info(f"搜索关键词列表: {queries}")
        
        all_results = []
        search_methods = [
            ('百度搜索', self.search_baidu),
            ('必应搜索', self.search_bing),
            ('搜狗搜索', self.search_sogou)
        ]
        
        def search_with_query(search_method_name, method, query):
            try:
                logger.info(f"启动{search_method_name}: {query}")
                return method(query)
            except Exception as e:
                logger.error(f"{search_method_name}({query})执行失败: {e}")
                return []
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            for query in queries:
                for search_name, method in search_methods:
                    future = executor.submit(search_with_query, search_name, method, query)
                    futures[future] = (search_name, query)
            
            for future in as_completed(futures):
                search_name, query = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    logger.info(f"{search_name}({query})完成，获得 {len(results)} 条结果")
                except Exception as e:
                    logger.error(f"{search_name}({query})执行失败: {e}")
        
        seen = set()
        unique_results = []
        has_context = any(person_info.get(field) for field in ('company', 'position', 'region'))
        minimum_score = 0.45 if has_context else 0.32
        for r in all_results:
            title = r.get('title', '')
            summary = r.get('summary', '')
            
            if not self._is_relevant(title, summary, person_info):
                continue

            score = 0
            name = person_info.get('name', '')
            if name and name in title:
                score += 0.4
            if name and name in (title + summary):
                score += 0.1
            if person_info.get('company') and person_info['company'] in (title + summary):
                score += 0.25
            if person_info.get('position') and person_info['position'] in (title + summary):
                score += 0.15
            if person_info.get('region') and person_info['region'] in (title + summary):
                score += 0.1
            if any(keyword in (title + summary) for keyword in ['采访', '履历', '任职', '任命', '入职', '离职', '人物', '报道', '专访', '创始人', '高管']):
                score += 0.1

            if score < minimum_score:
                continue
            
            key = title + r.get('url', '')
            if key not in seen:
                seen.add(key)
                r['relevance'] = min(score, 1.0)
                unique_results.append(r)
        
        unique_results = unique_results[:20]
        
        logger.info(f"搜索完成，共获取 {len(unique_results)} 条相关结果")
        return unique_results

if __name__ == '__main__':
    searcher = WebSearch()
    test_person = {
        'name': '马云',
        'company': '阿里巴巴',
    }
    results = searcher.search_all(test_person)
    print(f"搜索结果数量: {len(results)}")
    for r in results[:5]:
        print(f"标题: {r['title']}")
        print(f"来源: {r['source']}")
        print(f"摘要: {r['summary']}")
        print('---')