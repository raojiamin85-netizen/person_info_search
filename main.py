import sys
import traceback
from pathlib import Path
from search_module import WebSearch
from enterprise_module import EnterpriseSearch
from legal_module import LegalSearch
from report_module import ReportGenerator
from resume_parser import ResumeParser
from utils import validate_person_info, deduplicate_results, logger

class PersonInfoSearcher:
    def __init__(self):
        self.web_searcher = WebSearch()
        self.enterprise_searcher = EnterpriseSearch()
        self.legal_searcher = LegalSearch()
        self.report_generator = ReportGenerator()
        self.resume_parser = ResumeParser()
    
    def search(self, person_info):
        try:
            validate_person_info(person_info)
        except ValueError as e:
            logger.error(f"输入信息验证失败: {e}")
            raise
        
        logger.info(f"开始搜索个人信息: {person_info.get('name')}")
        
        all_results = {
            'news': [],
            'enterprise': [],
            'legal': []
        }
        
        try:
            logger.info("开始全网搜索...")
            news_results = self.web_searcher.search_all(person_info)
            news_results = deduplicate_results(news_results, person_info)
            all_results['news'] = news_results
            logger.info(f"全网搜索完成，获得 {len(news_results)} 条结果")
        except Exception as e:
            logger.error(f"全网搜索失败: {e}")
            traceback.print_exc()
        
        try:
            logger.info("开始企业信息查询...")
            enterprise_results = self.enterprise_searcher.search_all(person_info)
            enterprise_results = deduplicate_results(enterprise_results, person_info)
            all_results['enterprise'] = enterprise_results
            logger.info(f"企业信息查询完成，获得 {len(enterprise_results)} 条结果")
        except Exception as e:
            logger.error(f"企业信息查询失败: {e}")
            traceback.print_exc()
        
        try:
            logger.info("开始法律信息查询...")
            legal_results = self.legal_searcher.search_all(person_info)
            legal_results = deduplicate_results(legal_results, person_info, threshold=0.34)
            all_results['legal'] = legal_results
            logger.info(f"法律信息查询完成，获得 {len(legal_results)} 条结果")
        except Exception as e:
            logger.error(f"法律信息查询失败: {e}")
            traceback.print_exc()
        
        return all_results
    
    def generate_report(self, person_info, results, formats=None):
        return self.report_generator.generate(person_info, results, formats)
    
    def parse_resume_file(self, filepath):
        try:
            return self.resume_parser.parse(filepath)
        except Exception as e:
            logger.error(f"简历解析失败: {e}")
            raise


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg == '--cli':
            run_cli_mode()
        elif Path(arg).exists():
            run_file_mode(arg)
        else:
            print(f"错误: 文件不存在 - {arg}")
            print_usage()
    else:
        print_usage()


def print_usage():
    print("=" * 60)
    print("个人公开信息搜索系统")
    print("=" * 60)
    print()
    print("使用方法:")
    print("  1. 交互式输入: python main.py --cli")
    print("  2. 简历文件输入: python main.py <简历文件路径>")
    print()
    print("支持的简历格式:")
    print("  - Word文档 (.docx)")
    print("  - PDF文档 (.pdf)")
    print("  - 图片文件 (.jpg, .jpeg, .png, .bmp)")
    print("  - 文本文件 (.txt)")
    print()
    print("示例:")
    print("  python main.py --cli")
    print("  python main.py \"d:\\简历\\张三简历.pdf\"")
    print("  python main.py \"d:\\简历\\张三简历.docx\"")
    print("=" * 60)


def run_cli_mode():
    print("=" * 60)
    print("个人公开信息搜索系统 - 交互模式")
    print("=" * 60)
    
    person_info = {}
    person_info['name'] = input("请输入姓名: ").strip()
    person_info['company'] = input("请输入过往任职企业名称(可选): ").strip() or None
    person_info['position'] = input("请输入所任岗位(可选): ").strip() or None
    person_info['region'] = input("请输入所在地域(可选): ").strip() or None
    person_info['phone'] = input("请输入电话号码(可选): ").strip() or None
    
    execute_search(person_info)


def run_file_mode(filepath):
    print("=" * 60)
    print("个人公开信息搜索系统 - 文件模式")
    print("=" * 60)
    print(f"\n正在解析简历文件: {filepath}")
    
    searcher = PersonInfoSearcher()
    
    try:
        person_info = searcher.parse_resume_file(filepath)
        
        print("\n解析结果:")
        print("-" * 40)
        if person_info.get('name'):
            print(f"姓名: {person_info['name']}")
        if person_info.get('phone'):
            print(f"电话: {person_info['phone']}")
        if person_info.get('email'):
            print(f"邮箱: {person_info['email']}")
        if person_info.get('company'):
            print(f"公司: {person_info['company']}")
        if person_info.get('position'):
            print(f"岗位: {person_info['position']}")
        if person_info.get('region'):
            print(f"地域: {person_info['region']}")
        print("-" * 40)
        
        if not person_info.get('name'):
            print("\n错误: 无法从简历中提取姓名")
            print("请手动输入姓名或使用交互模式")
            name = input("请输入姓名: ").strip()
            if name:
                person_info['name'] = name
            else:
                return
        
        confirm = input("\n确认使用上述信息进行搜索？(y/n): ").strip().lower()
        if confirm != 'y':
            return
        
        execute_search(person_info)
        
    except Exception as e:
        print(f"\n简历解析失败: {e}")
        logger.error(f"简历解析失败: {e}")
        traceback.print_exc()


def execute_search(person_info):
    print("\n开始搜索，请稍候...")
    
    try:
        searcher = PersonInfoSearcher()
        results = searcher.search(person_info)
        
        print("\n" + "=" * 60)
        print("搜索结果汇总")
        print("=" * 60)
        
        if results['news']:
            print(f"\n【网络新闻及自媒体报道】共 {len(results['news'])} 条")
            for i, item in enumerate(results['news'][:5], 1):
                print(f"\n{i}. {item['title']}")
                print(f"   来源: {item['source']}")
                print(f"   相关度: {item.get('relevance', 'N/A')}")
        
        if results['enterprise']:
            print(f"\n【关联企业信息】共 {len(results['enterprise'])} 条")
            for i, item in enumerate(results['enterprise'][:5], 1):
                print(f"\n{i}. {item.get('company_name', item.get('title', ''))}")
                print(f"   来源: {item['source']}")
                if item.get('legal_person'):
                    print(f"   法定代表人: {item['legal_person']}")
        
        if results['legal']:
            print(f"\n【法律信息】共 {len(results['legal'])} 条")
            for i, item in enumerate(results['legal'], 1):
                print(f"\n{i}. {item['title']}")
                print(f"   来源: {item['source']}")
                if item.get('note'):
                    print(f"   备注: {item['note']}")
        
        if not results['news'] and not results['enterprise'] and not results['legal']:
            print("\n未找到任何相关信息")
        
        print("\n" + "=" * 60)
        export_choice = input("是否生成报告？(y/n): ").strip().lower()
        if export_choice == 'y':
            formats = input("请选择输出格式(可多选，用逗号分隔): excel, word, json\n").strip().split(',')
            formats = [f.strip() for f in formats if f.strip()]
            if not formats:
                formats = ['excel']
            
            print("\n正在生成报告...")
            output_files = searcher.generate_report(person_info, results, formats)
            print("\n报告生成完成:")
            for fmt, path in output_files.items():
                print(f"  {fmt}: {path}")
    
    except Exception as e:
        print(f"\n搜索过程中发生错误: {e}")
        logger.error(f"搜索失败: {e}")
        traceback.print_exc()


if __name__ == '__main__':
    main()