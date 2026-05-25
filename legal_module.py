import requests
import time
import random
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from config import LEGAL_URLS, DEFAULT_HEADERS, SEARCH_TIMEOUT, REQUEST_DELAY, MAX_SEARCH_RESULTS
from utils import clean_text, logger

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

class LegalSearch:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.render_mode = self._is_render_env()
        
        self.use_selenium = False
        if self.render_mode:
            logger.info("检测到 Render 环境，法律查询将使用轻量模式")
            return

        try:
            from selenium import webdriver
            self.use_selenium = True
            logger.info("LegalSearch: Selenium已加载")
        except ImportError:
            pass

    def _is_render_env(self):
        return bool(
            os.environ.get('RENDER')
            or os.environ.get('RENDER_SERVICE_ID')
            or os.environ.get('RENDER_EXTERNAL_URL')
        )
    
    def _build_query(self, person_info, keywords):
        name = person_info.get('name', '')
        company = person_info.get('company', '')
        position = person_info.get('position', '')
        region = person_info.get('region', '')

        parts = [name]
        if company:
            parts.append(company)
        if position:
            parts.append(position)
        if region:
            parts.append(region)
        parts.append(keywords)
        return ' '.join([part for part in parts if part])

    def _is_relevant_result(self, title, summary, person_info, source_name):
        name = person_info.get('name', '')
        company = person_info.get('company', '')
        text = f'{title} {summary}'

        legal_keywords = ['裁判文书', '判决书', '裁定书', '执行', '被执行人', '失信', '限制消费', '开庭公告', '审判流程', '法院公告', '拍卖公告', '案号', '案由', '法院', '当事人']
        noise_keywords = ['招聘', '培训', '下载', '小说', '游戏', '图片', '壁纸', '百科', '新闻', '资讯', '科普']

        if any(keyword in text for keyword in noise_keywords):
            return False

        if not any(keyword in text for keyword in legal_keywords):
            return False

        if name and name in text:
            return True

        if company and company in text:
            return True

        if any(keyword in text for keyword in ['案号', '法院', '执行', '失信', '限制消费', '开庭公告', '审判流程', '裁判文书', '拍卖公告']):
            return True

        return False

    def _score_legal_result(self, title, summary, person_info, source_name):
        text = f'{title} {summary}'
        name = person_info.get('name', '')
        company = person_info.get('company', '')
        position = person_info.get('position', '')
        score = 0.0

        if name and name in text:
            score += 0.4
        if company and company in text:
            score += 0.18
        if position and position in text:
            score += 0.06

        if any(keyword in text for keyword in ['案号', '法院', '案由', '当事人', '判决', '裁定']):
            score += 0.22
        if any(keyword in text for keyword in ['执行', '失信', '限制消费', '终本', '开庭公告', '审判流程', '法院公告']):
            score += 0.18

        if source_name == '中国裁判文书网':
            score += 0.05
        if source_name == '中国执行信息公开网':
            score += 0.05

        return min(score, 1.0)

    def _search_with_engine(self, person_info, keywords, source_name, num_results=5):
        results = []
        try:
            query = self._build_query(person_info, keywords)
            
            if self.use_selenium:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                
                chrome_options = Options()
                chrome_options.add_argument('--headless=new')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
                
                driver = webdriver.Chrome(options=chrome_options)
                try:
                    driver.get(f'https://www.baidu.com/s?wd={query}')
                    time.sleep(random.uniform(2, 4))
                    
                    soup = BeautifulSoup(driver.page_source, 'lxml')
                    items = soup.find_all('div', class_='result') or soup.find_all('div', class_='c-container')
                    
                    for item in items[:num_results]:
                        title_tag = item.find('h3')
                        link_tag = item.find('a')
                        summary_tag = item.find('p', class_='c-abstract')
                        
                        if title_tag and link_tag:
                            title = clean_text(title_tag.get_text())
                            summary = clean_text(summary_tag.get_text()) if summary_tag else ''
                            if not self._is_relevant_result(title, summary, person_info, source_name):
                                continue

                            result = {
                                'title': title,
                                'url': link_tag.get('href'),
                                'summary': summary,
                                'source': source_name,
                                'type': 'legal',
                            }
                            result['relevance'] = self._score_legal_result(title, summary, person_info, source_name)
                            if result['relevance'] < 0.35:
                                continue
                            if '案号' in f'{title} {summary}':
                                match = re.search(r'([（(]?\d{4}[）)]?[^\s]{0,12}号)', f'{title} {summary}')
                                if match:
                                    result['note'] = f'案号: {clean_text(match.group(1))}'
                            results.append(result)
                finally:
                    driver.quit()
            else:
                url = f'https://www.baidu.com/s?wd={query}'
                self.session.headers['User-Agent'] = random.choice(USER_AGENTS)
                response = self.session.get(url, timeout=SEARCH_TIMEOUT)
                
                soup = BeautifulSoup(response.text, 'lxml')
                items = soup.find_all('div', class_='result') or soup.find_all('div', class_='c-container')
                
                for item in items[:num_results]:
                    title_tag = item.find('h3')
                    link_tag = item.find('a')
                    summary_tag = item.find('p', class_='c-abstract')
                    
                    if title_tag and link_tag:
                        title = clean_text(title_tag.get_text())
                        summary = clean_text(summary_tag.get_text()) if summary_tag else ''
                        if not self._is_relevant_result(title, summary, person_info, source_name):
                            continue

                        result = {
                            'title': title,
                            'url': link_tag.get('href'),
                            'summary': summary,
                            'source': source_name,
                            'type': 'legal'
                        }
                        result['relevance'] = self._score_legal_result(title, summary, person_info, source_name)
                        if result['relevance'] < 0.35:
                            continue
                        if '案号' in f'{title} {summary}':
                            match = re.search(r'([（(]?\d{4}[）)]?[^\s]{0,12}号)', f'{title} {summary}')
                            if match:
                                result['note'] = f'案号: {clean_text(match.group(1))}'
                        results.append(result)
            
            logger.info(f"{source_name}搜索完成，获得 {len(results)} 条结果")
        except Exception as e:
            logger.error(f"{source_name}搜索失败: {e}")
        
        return results
    
    def search_wenshu(self, person_info, num_results=5):
        return self._search_with_engine(person_info, '裁判文书 判决书', '中国裁判文书网', 3 if self.render_mode else num_results)
    
    def search_court(self, person_info, num_results=5):
        return self._search_with_engine(person_info, '开庭公告 审判流程', '中国审判流程信息公开网', 3 if self.render_mode else num_results)
    
    def search_zxgk(self, person_info, num_results=5):
        return self._search_with_engine(person_info, '被执行人 失信名单 限制消费', '中国执行信息公开网', 3 if self.render_mode else num_results)
    
    def search_gonggao(self, person_info, num_results=5):
        return self._search_with_engine(person_info, '法院公告 拍卖公告', '人民法院公告网', 3 if self.render_mode else num_results)
    
    def search_gsxt(self, person_info, num_results=5):
        return self._search_with_engine(person_info, '企业失信 经营异常 行政处罚', '国家企业信用信息公示系统', 3 if self.render_mode else num_results)
    
    def search_all(self, person_info):
        all_results = []
        
        search_methods = [
            ('中国裁判文书网', self.search_wenshu),
            ('中国审判流程信息公开网', self.search_court),
            ('中国执行信息公开网', self.search_zxgk),
            ('人民法院公告网', self.search_gonggao),
            ('国家企业信用信息公示系统', self.search_gsxt)
        ]

        if self.render_mode:
            search_methods = search_methods[:2]
        
        with ThreadPoolExecutor(max_workers=1 if self.render_mode else 2) as executor:
            futures = {}
            for source_name, method in search_methods:
                logger.info(f"启动{source_name}查询...")
                future = executor.submit(method, person_info)
                futures[future] = source_name
            
            for future in as_completed(futures):
                source_name = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    logger.info(f"{source_name}完成，获得 {len(results)} 条结果")
                except Exception as e:
                    logger.error(f"{source_name}查询失败: {e}")
        
        seen = set()
        unique_results = []
        for result in all_results:
            key = f"{result.get('title', '')}|{result.get('url', '')}|{result.get('source', '')}"
            if key in seen:
                continue
            seen.add(key)
            unique_results.append(result)

        unique_results.sort(key=lambda item: item.get('relevance', 0), reverse=True)
        if self.render_mode:
            unique_results = unique_results[:5]
        return unique_results

if __name__ == '__main__':
    searcher = LegalSearch()
    test_person = {'name': '张三'}
    results = searcher.search_all(test_person)
    print(f"法律信息查询结果数量: {len(results)}")
    for r in results:
        print(f"标题: {r['title']}")
        print(f"来源: {r['source']}")
        if r.get('note'):
            print(f"备注: {r['note']}")
        print('---')