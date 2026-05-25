import requests
import time
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from config import DEFAULT_HEADERS, SEARCH_TIMEOUT, REQUEST_DELAY
from utils import clean_text, logger

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
]

class EnterpriseSearch:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.use_selenium = False
        
        try:
            from selenium import webdriver
            self.use_selenium = True
            logger.info("EnterpriseSearch: Selenium已加载")
        except ImportError:
            logger.warning("EnterpriseSearch: Selenium未安装")
    
    def _is_valid_company_name(self, name):
        if not name or len(name) < 2:
            return False
        
        if name.isdigit():
            return False
        
        if len(name) > 50:
            return False
        
        valid_keywords = ['公司', '集团', '企业', '科技', '有限', '股份', '责任', '投资', '控股', '网络', '信息', '软件', '数据']
        for keyword in valid_keywords:
            if keyword in name:
                return True
        
        if '(' in name or '（' in name:
            return True
        
        return False

    def _build_queries(self, person_info):
        name = person_info.get('name', '')
        company = person_info.get('company', '')
        position = person_info.get('position', '')
        region = person_info.get('region', '')

        queries = []

        if company:
            queries.extend([
                f'{company} 企查查 法定代表人 股东 注册资本 统一社会信用代码',
                f'{company} 天眼查 经营范围 企业状态 注册资本',
                f'{company} 爱企查 法定代表人 股东 经营范围',
            ])

        if name and company:
            queries.extend([
                f'{name} {company} 任职 企业',
                f'{name} {company} 法定代表人 股东',
            ])

        if name and position:
            queries.append(f'{name} {position} 任职 企业')

        if name and region:
            queries.append(f'{name} {region} 企业')

        if company:
            queries.append(f'{company} 工商信息')
        if name:
            queries.append(f'{name} 企查查')
            queries.append(f'{name} 天眼查')

        unique_queries = []
        seen = set()
        for query in queries:
            if query not in seen:
                seen.add(query)
                unique_queries.append(query)

        return unique_queries
    
    def _extract_position(self, title, summary):
        positions = ['法人', '法定代表人', '股东', '创始人', '董事长', '总经理', 'CEO', '高管', '监事', '董事']
        found_positions = []
        
        for pos in positions:
            if pos in title or (summary and pos in summary):
                found_positions.append(pos)
        
        return ','.join(found_positions) if found_positions else '未明确'

    def _extract_company_details(self, title, summary):
        text = f'{title} {summary}'
        details = {
            'legal_person': '',
            'shareholders': '',
            'registration': '',
            'status': '',
            'address': '',
            'business_scope': '',
            'credit_code': '',
            'description': ''
        }

        patterns = {
            'legal_person': [r'法定代表人[:：]?([^，。,；;\s]{2,20})', r'法人[:：]?([^，。,；;\s]{2,20})'],
            'shareholders': [r'股东[:：]?([^，。；;]{2,40})', r'持股[:：]?([^，。；;]{2,40})'],
            'registration': [r'注册资本[:：]?([^，。；;]{2,30})', r'成立日期[:：]?([^，。；;]{4,20})'],
            'status': [r'企业状态[:：]?([^，。；;]{2,20})', r'经营状态[:：]?([^，。；;]{2,20})'],
            'address': [r'注册地址[:：]?([^，。；;]{2,40})', r'地址[:：]?([^，。；;]{2,40})'],
            'business_scope': [r'经营范围[:：]?([^。；;]{4,120})', r'主营业务[:：]?([^。；;]{4,120})'],
            'credit_code': [r'统一社会信用代码[:：]?([^，。；;\s]{10,30})'],
        }

        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, text)
                if match:
                    details[field] = clean_text(match.group(1))
                    break

        description_parts = []
        for keyword in ['经营范围', '企业状态', '经营状态', '成立于', '注册地址', '地址', '主营', '行业', '融资', '统一社会信用代码']:
            if keyword in text:
                description_parts.append(keyword)

        if summary:
            description_parts.append(summary[:160])

        details['description'] = '；'.join([part for part in description_parts if part])
        return details

    def _is_relevant_result(self, title, summary, person_info):
        company = person_info.get('company', '')
        name = person_info.get('name', '')
        text = f'{title} {summary}'
        enterprise_keywords = ['企查查', '天眼查', '爱企查', '工商', '注册资本', '法定代表人', '股东', '经营范围', '企业状态', '统一社会信用代码']

        if company and company in text:
            return True

        if name and company and name in text and any(keyword in text for keyword in enterprise_keywords):
            return True

        if any(keyword in text for keyword in enterprise_keywords):
            return True

        return False

    def _score_enterprise_result(self, result, person_info):
        text = ' '.join(
            str(result.get(field, '')) for field in (
                'company_name', 'summary', 'description', 'legal_person', 'shareholders',
                'registration', 'status', 'address', 'business_scope', 'credit_code', 'position'
            )
        )
        score = 0.0
        company = person_info.get('company', '')
        name = person_info.get('name', '')
        position = person_info.get('position', '')
        region = person_info.get('region', '')

        if company and company in text:
            score += 0.35
        if name and name in text:
            score += 0.15
        if position and position in text:
            score += 0.08
        if region and region in text:
            score += 0.05

        if any(keyword in text for keyword in ['法定代表人', '股东', '注册资本', '经营范围', '统一社会信用代码', '企业状态']):
            score += 0.25

        if any(keyword in result.get('source', '') for keyword in ['企查查', '天眼查', '爱企查']):
            score += 0.1

        return min(score, 1.0)
    
    def _search_with_selenium(self, query, person_info, num_results=10):
        results = []
        if not self.use_selenium:
            return results
            
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
            
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                driver.get(f'https://www.baidu.com/s?wd={query}')
                time.sleep(random.uniform(3, 5))
                
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'lxml')
                
                items = soup.find_all('div', class_='result') or soup.find_all('div', class_='c-container')
                
                for item in items[:num_results]:
                    title_tag = item.find('h3')
                    link_tag = item.find('a')
                    summary_tag = item.find('p', class_='c-abstract')
                    
                    if title_tag and link_tag:
                        title_text = clean_text(title_tag.get_text())
                        summary_text = clean_text(summary_tag.get_text()) if summary_tag else ''
                        
                        if not self._is_valid_company_name(title_text):
                            continue

                        if not self._is_relevant_result(title_text, summary_text, person_info):
                            continue
                        
                        position = self._extract_position(title_text, summary_text)
                        details = self._extract_company_details(title_text, summary_text)
                        
                        source_name = '企业查询'
                        if '企查查' in title_text or 'qcc' in link_tag.get('href', ''):
                            source_name = '企查查'
                        elif '天眼查' in title_text or 'tianyancha' in link_tag.get('href', ''):
                            source_name = '天眼查'
                        elif '爱企查' in title_text or 'aiqicha' in link_tag.get('href', ''):
                            source_name = '爱企查'
                        
                        result = {
                            'company_name': title_text,
                            'url': link_tag.get('href', ''),
                            'legal_person': details.get('legal_person', ''),
                            'shareholders': details.get('shareholders', ''),
                            'registration': details.get('registration', ''),
                            'status': details.get('status', ''),
                            'address': details.get('address', ''),
                            'business_scope': details.get('business_scope', ''),
                            'credit_code': details.get('credit_code', ''),
                            'position': position,
                            'summary': summary_text[:200] if summary_text else '',
                            'description': details.get('description', ''),
                            'source': source_name,
                            'type': 'enterprise'
                        }
                        result['relevance'] = self._score_enterprise_result(result, person_info)
                        if result['relevance'] < 0.35:
                            continue
                        results.append(result)
                
                logger.info(f"Selenium企业搜索完成，获得 {len(results)} 条结果")
            finally:
                driver.quit()
                
        except Exception as e:
            logger.error(f"Selenium企业搜索失败: {e}")
        
        return results
    
    def search_all(self, person_info):
        search_queries = self._build_queries(person_info)
        
        all_results = []
        
        for query in search_queries:
            logger.info(f"企业搜索: {query}")
            results = self._search_with_selenium(query, person_info)
            all_results.extend(results)
            time.sleep(REQUEST_DELAY)
        
        seen = set()
        unique_results = []
        for r in all_results:
            key = f"{r['company_name']}|{r.get('legal_person', '')}|{r.get('credit_code', '')}|{r.get('source', '')}"
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        unique_results.sort(key=lambda item: item.get('relevance', 0), reverse=True)
        
        logger.info(f"企业搜索完成，共获取 {len(unique_results)} 条去重结果")
        return unique_results

if __name__ == '__main__':
    searcher = EnterpriseSearch()
    test_person = {
        'name': '马云',
        'company': '阿里巴巴'
    }
    results = searcher.search_all(test_person)
    print(f"企业查询结果数量: {len(results)}")
    for r in results[:5]:
        print(f"公司名称: {r['company_name']}")
        print(f"职务: {r['position']}")
        print(f"来源: {r['source']}")
        print('---')