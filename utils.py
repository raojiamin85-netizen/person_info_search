import os
import re
import logging
from datetime import datetime
from fuzzywuzzy import fuzz, process
from config import LOG_DIR, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\-_.，,。.、/\\]', '', text)
    return text.strip()


def _normalize_text(value):
    return clean_text(str(value)) if value else ""


def _result_text(result):
    fields = [
        result.get('title'),
        result.get('summary'),
        result.get('company_name'),
        result.get('description'),
        result.get('legal_person'),
        result.get('shareholders'),
        result.get('position'),
        result.get('note'),
        result.get('status'),
        result.get('address'),
        result.get('business_scope'),
        result.get('credit_code'),
        result.get('case_number'),
        result.get('court'),
        result.get('cause'),
        result.get('party_role'),
    ]
    return _normalize_text(' '.join(_normalize_text(field) for field in fields if field))

def extract_phone(text):
    pattern = r'1[3-9]\d{9}'
    matches = re.findall(pattern, text)
    return list(set(matches))

def extract_email(text):
    pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    matches = re.findall(pattern, text)
    return list(set(matches))

def extract_company(text):
    keywords = ['公司', '集团', '有限', '股份', '科技', '实业', '贸易', '投资']
    pattern = r'([\u4e00-\u9fa5a-zA-Z]+(?:公司|集团|有限|股份|科技|实业|贸易|投资)[\u4e00-\u9fa5a-zA-Z]*)'
    matches = re.findall(pattern, text)
    return [m.strip() for m in matches]

def calculate_similarity(str1, str2):
    if not str1 or not str2:
        return 0
    return fuzz.token_sort_ratio(str1, str2) / 100


def calculate_result_relevance(result, person_info):
    result_text = _result_text(result)
    if not result_text:
        return 0

    name = _normalize_text(person_info.get('name'))
    company = _normalize_text(person_info.get('company'))
    position = _normalize_text(person_info.get('position'))
    region = _normalize_text(person_info.get('region'))

    score = 0.0

    if name:
        if name in result_text:
            score += 0.42
        else:
            score += max(fuzz.partial_ratio(name, result_text) / 100 * 0.28, 0)

    if company:
        if company in result_text:
            score += 0.28
        else:
            score += max(fuzz.partial_ratio(company, result_text) / 100 * 0.2, 0)

    if position:
        if position in result_text:
            score += 0.14
        else:
            score += max(fuzz.partial_ratio(position, result_text) / 100 * 0.1, 0)

    if region:
        if region in result_text:
            score += 0.08
        else:
            score += max(fuzz.partial_ratio(region, result_text) / 100 * 0.05, 0)

    if result.get('type') == 'enterprise':
        enterprise_keywords = ['法人', '法定代表人', '股东', '高管', '监事', '注册资本', '成立日期', '经营范围', '企业状态', '统一社会信用代码', '经营状态']
        if any(keyword in result_text for keyword in enterprise_keywords):
            score += 0.16

    if result.get('type') == 'legal':
        legal_keywords = ['裁判', '执行', '公告', '审判', '失信', '限高', '案号', '案由', '法院', '当事人']
        if any(keyword in result_text for keyword in legal_keywords):
            score += 0.18

    if name and len(name) <= 2 and company:
        score *= 1.05

    if name and name not in result_text and company and company not in result_text:
        score *= 0.7

    return min(score, 1.0)

def is_similar(str1, str2, threshold=None):
    threshold = threshold or SIMILARITY_THRESHOLD
    return calculate_similarity(str1, str2) >= threshold

def match_person(info1, info2):
    score = 0
    total = 0
    
    if info1.get('name') and info2.get('name'):
        score += calculate_similarity(info1['name'], info2['name']) * 0.4
        total += 0.4
    
    if info1.get('company') and info2.get('company'):
        score += calculate_similarity(info1['company'], info2['company']) * 0.3
        total += 0.3
    
    if info1.get('position') and info2.get('position'):
        score += calculate_similarity(info1['position'], info2['position']) * 0.2
        total += 0.2
    
    if info1.get('region') and info2.get('region'):
        score += calculate_similarity(info1['region'], info2['region']) * 0.1
        total += 0.1
    
    return score / total if total > 0 else 0

def deduplicate_results(results, person_info, threshold=None):
    if threshold is None:
        has_context = any(person_info.get(field) for field in ('company', 'position', 'region'))
        if any(os.environ.get(key) for key in ('RENDER', 'RENDER_SERVICE_ID', 'RENDER_EXTERNAL_URL')):
            threshold = 0.15
        else:
            threshold = 0.42 if has_context else 0.3
    unique_results = []
    seen_keys = set()
    
    for result in results:
        title = (result.get('title') or '').lower()
        company_name = (result.get('company_name') or '').lower()
        url = (result.get('url') or '').lower()
        credit_code = (result.get('credit_code') or '').lower()
        source = (result.get('source') or '').lower()

        if title:
            key = f"title|{title}|{source}"
        elif company_name:
            key = f"company|{company_name}|{credit_code}|{source}"
        elif url:
            key = f"url|{url}|{source}"
        else:
            key = f"fallback|{source}|{len(unique_results)}"

        if key in seen_keys:
            continue
        
        seen_keys.add(key)
        
        relevance = calculate_result_relevance(result, person_info)
        if relevance < threshold:
            continue

        result['relevance'] = relevance
        
        unique_results.append(result)
    
    unique_results.sort(key=lambda x: x.get('relevance', 0), reverse=True)
    return unique_results

def validate_person_info(person_info):
    required_fields = ['name']
    missing = [f for f in required_fields if not person_info.get(f)]
    if missing:
        raise ValueError(f"缺少必要字段: {', '.join(missing)}")
    
    if person_info.get('phone'):
        if not re.match(r'1[3-9]\d{9}', person_info['phone']):
            raise ValueError("电话号码格式不正确")
    
    return True

def format_date(date_str):
    if not date_str:
        return ""
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        return date.strftime('%Y年%m月%d日')
    except:
        return date_str

def get_current_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def generate_report_id():
    return datetime.now().strftime('%Y%m%d%H%M%S')