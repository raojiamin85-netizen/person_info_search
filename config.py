import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

SEARCH_URLS = {
    'baidu': 'https://www.baidu.com/s',
    'bing': 'https://www.bing.com/search',
    'sougou': 'https://www.sogou.com/web',
}

LEGAL_URLS = {
    'wenshu': 'https://wenshu.court.gov.cn/',
    'court': 'https://splcgk.court.gov.cn/',
    'zxgk': 'http://zxgk.court.gov.cn/',
    'gonggao': 'https://rmfygg.court.gov.cn/',
    'gsxt': 'http://www.gsxt.gov.cn/',
}

ENTERPRISE_URLS = {
    'qcc': 'https://www.qcc.com/',
    'aiqicha': 'https://aiqicha.baidu.com/',
    'tianyancha': 'https://www.tianyancha.com/',
}

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

SEARCH_TIMEOUT = 20
REQUEST_DELAY = 1

SIMILARITY_THRESHOLD = 0.7
MAX_SEARCH_RESULTS = 10

EXPORT_FORMATS = ['excel', 'word', 'json']