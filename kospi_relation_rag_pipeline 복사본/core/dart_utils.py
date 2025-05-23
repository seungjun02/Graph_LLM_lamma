# core/dart_utils.py (v5 - 최종: 섹션 추출 + 기존 함수 유지)

import os
import re
import traceback
import zipfile
import io
import requests # 필요시 사용
from bs4 import BeautifulSoup # decode_content 에서 사용
try:
    from lxml import etree # XML/HTML 파싱용
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
    print("CRITICAL ERROR: lxml 라이브러리가 필요합니다. 'pip install lxml' 로 설치해주세요. XML 파싱이 불가능합니다.")

try:
    import dart_fss as dart
except ImportError:
    print("ERROR: dart-fss 라이브러리가 설치되지 않았습니다. pip install dart-fss")
    dart = None

from tenacity import retry, stop_after_attempt, wait_fixed

# --- config.py 에서 설정값 가져오기 ---
try:
    # 로거와 재시도 설정만 가져옴
    from config import logger, RETRY_ATTEMPTS, RETRY_WAIT_SECONDS
    # TARGET_REPORT_CODES는 여기서 직접 사용 안 함 (상위에서 필터링)
except ImportError:
    import logging
    # 로거 이름 통일 (메인 노트북과 동일하게)
    logger = logging.getLogger("KospiRAGPipeline")
    logger.warning("config.py 로드 실패. dart_utils에서 기본 로거 및 재시도 설정 사용.")
    # 기본값 설정
    RETRY_ATTEMPTS = 3
    RETRY_WAIT_SECONDS = 5
    # 핸들러 없으면 추가 (경고 방지용)
    if not logger.hasHandlers():
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.NullHandler())


# --- download_document 함수 임포트 ---
DOWNLOAD_FUNC_AVAILABLE = False
if dart: # dart_fss 임포트 성공 시에만 시도
    try:
        from dart_fss.api.filings import download_document
        DOWNLOAD_FUNC_AVAILABLE = True
        logger.info("dart_fss.api.filings.download_document imported successfully.")
    except ImportError:
        logger.error("dart_fss.api.filings.download_document import 실패. dart-fss 버전 또는 설치를 확인하세요.")

# === 보고서 검색, 다운로드, ZIP 추출, 디코딩 함수 ===
# 이 함수들은 파일 처리의 앞단에서 필요하므로 유지합니다.

@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_fixed(RETRY_WAIT_SECONDS))
def find_latest_annual_report(corp_code, year, report_codes=['11011']): # 기본값을 사업보고서로 변경 가능
    """ 특정 기업의 지정된 연도 최신 정기보고서(기본: 사업보고서) 객체를 찾습니다. """
    if not dart: raise ImportError("dart-fss 모듈 로드 실패")
    report_type_name = ','.join(report_codes) if report_codes else 'any'
    logger.debug(f"Searching for report: corp={corp_code}, year={year}, codes={report_type_name}")
    try:
        #dart.filings.search(...) # dart-fss 라이브러리 사용법에 맞게 호출
        reports = dart.filings.search(
            corp_code=corp_code, bgn_de=f"{year}0101", end_de=f"{year}1231",
            pblntf_ty='A', # 정기공시
            pblntf_detail_ty=report_codes, # 대상 보고서 코드
            sort='date', sort_mth='desc', page_count=1 # 최신 1건
        )
        if reports and reports.list: # dart-fss 버전에 따라 .list 확인 필요할 수 있음
            latest_report = reports.list[0]
            logger.info(f"{corp_code}({year}) 최신 보고서({latest_report.report_nm}) 찾음: rcept_no={latest_report.rcept_no}")
            return latest_report
        else:
            logger.warning(f"{corp_code}({year}) 대상 보고서({report_type_name}) 없음.")
            return None
    except Exception as e:
        logger.error(f"{corp_code} 보고서 검색 오류: {e.__class__.__name__} - {e}", exc_info=True)
        raise # 오류 재발생시켜 @retry 작동

@retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_fixed(RETRY_WAIT_SECONDS))
def download_report_file(rcept_no, download_path):
    """ 지정된 접수번호의 공시서류 원본파일(ZIP)을 다운로드하고 검증합니다. """
    if not DOWNLOAD_FUNC_AVAILABLE: raise ImportError("download_document 함수 사용 불가")
    if not rcept_no: raise ValueError("다운로드할 rcept_no 없음")
    logger.info(f"다운로드 시도: rcept_no={rcept_no}, path={download_path}")
    file_path = None
    try:
        os.makedirs(download_path, exist_ok=True)
        # dart-fss의 download_document 사용
        file_path = download_document(path=download_path, rcept_no=rcept_no)

        # 검증
        if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 100: # 최소 크기 지정
            try:
                with zipfile.ZipFile(file_path, 'r') as zf: _ = zf.namelist()
                logger.info(f"보고서 {rcept_no} 다운로드 및 ZIP 검증 완료: {file_path}")
                return file_path
            except zipfile.BadZipFile: logger.error(f"다운로드 실패: BadZipFile ({file_path})"); return None
            except Exception as zip_err: logger.error(f"ZIP 검증 오류: {zip_err} ({file_path})"); return None
        else:
            size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 'N/A'
            logger.error(f"다운로드 실패: 파일 없음/빔 (Path: {file_path}, Size: {size} bytes)")
            # 실패 시 빈 파일 삭제 (선택적)
            if file_path and os.path.exists(file_path) and size == 0:
                try: os.remove(file_path); logger.info(f"Removed empty file: {file_path}")
                except OSError as rm_err: logger.warning(f"Failed to remove empty file: {rm_err}")
            return None
    except Exception as e:
        logger.error(f"다운로드 중 예외 발생 (rcept_no={rcept_no}): {e.__class__.__name__} - {e}", exc_info=True)
        raise # 오류 재발생

def extract_report_file_from_zip(zip_file_path, extract_dir_base):
    """ ZIP 파일에서 보고서 파일(XML 우선)을 찾아 임시 폴더에 압축 해제 후 경로 반환 """
    if not zip_file_path or not os.path.exists(zip_file_path) or not zipfile.is_zipfile(zip_file_path):
        logger.error(f"유효하지 않은 ZIP 파일 경로: {zip_file_path}")
        return None, None

    extract_dir = None
    try:
        # 압축 해제 폴더 생성 (기존 내용 삭제)
        report_name = os.path.splitext(os.path.basename(zip_file_path))[0]
        extract_dir = os.path.join(extract_dir_base, report_name + "_extracted")
        if os.path.exists(extract_dir): shutil.rmtree(extract_dir)
        os.makedirs(extract_dir)

        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
            logger.debug(f"ZIP 압축 해제 완료: {extract_dir}")

            all_files = [os.path.join(extract_dir, f) for f in zip_ref.namelist()]
            # 1순위: 루트의 XML 파일
            xml_files = [f for f in all_files if f.lower().endswith('.xml') and os.path.dirname(f) == extract_dir]
            if xml_files:
                 target_file = xml_files[0]
                 logger.info(f"Root XML file found: {os.path.basename(target_file)}")
                 return target_file, '.xml'
            # 2순위: 루트의 HTML 계열 파일
            html_files = [f for f in all_files if f.lower().endswith(('.html', '.htm')) and os.path.dirname(f) == extract_dir]
            if html_files:
                 target_file = html_files[0]
                 logger.warning(f"XML not found, using root HTML file: {os.path.basename(target_file)}")
                 return target_file, os.path.splitext(target_file)[1].lower()
            # 3순위: 하위 폴더 포함 모든 XML/HTML 파일 중 가장 큰 파일 ( heuristics )
            candidates = [f for f in all_files if f.lower().endswith(('.xml', '.html', '.htm'))]
            if candidates:
                 target_file = max(candidates, key=os.path.getsize)
                 logger.warning(f"Using largest XML/HTML file found: {os.path.relpath(target_file, extract_dir_base)}")
                 # !!! 수정: extract_dir도 반환하도록 변경 !!!
                 return target_file, os.path.splitext(target_file)[1].lower(), extract_dir

            logger.error(f"No suitable report file (XML/HTML) found in ZIP: {zip_file_path}")
            # !!! 수정: 실패 시에도 extract_dir 반환 (None 처리) !!!
            return None, None, extract_dir

    except Exception as e:
        logger.error(f"Error extracting from ZIP ({zip_file_path}): {e}", exc_info=True)
        # !!! 수정: 오류 발생 시에도 extract_dir 반환 (None 처리) !!!
        return None, None, extract_dir
    # finally 블록은 필요 없음 (상위에서 처리)

def decode_content(report_bytes, encoding_hint=None):
    """ 바이트 내용을 추측 또는 명시된 인코딩으로 디코딩 (개선) """
    if not report_bytes: return ""
    # ... (이전 답변의 decode_content 함수 내용 유지) ...
    detected_encoding = None
    try:
        if report_bytes.startswith(b'\xef\xbb\xbf'): return report_bytes[3:].decode('utf-8', errors='replace')
        try: # bs4 이용
            soup_temp = BeautifulSoup(report_bytes, 'lxml', from_encoding=encoding_hint)
            original_encoding = soup_temp.original_encoding
            if original_encoding:
                detected_encoding = original_encoding.lower().replace('ks_c_5601-1987', 'cp949').replace('euc_kr', 'cp949').replace('windows-949', 'cp949')
                logger.info(f"Encoding detected by parser: {detected_encoding}")
                return report_bytes.decode(detected_encoding, errors='replace')
        except Exception: pass
        # 직접 시도
        for enc in ['utf-8', 'cp949', 'euc-kr']:
             try: return report_bytes.decode(enc); logger.info(f"Decoded with '{enc}'.")
             except UnicodeDecodeError: continue
        # 최후
        logger.warning(f"Encoding detection failed. Falling back to utf-8 replace.")
        return report_bytes.decode('utf-8', errors='replace')
    except Exception as e: logger.error(f"Content decoding error: {e}"); return ""

# === XML 파싱 관련 함수 (섹션 단위 추출용) ===

def _get_text_content_lxml(element):
    """ lxml 요소와 그 모든 자식 요소들의 텍스트를 결합 (개선) """
    if element is None: return ""
    try:
        # itertext() 사용 및 공백 정규화
        text_parts = [text.strip() for text in element.itertext() if text and text.strip()]
        full_text = ' '.join(text_parts)
        return full_text
    except Exception as e:
        logger.warning(f"Element text extraction error: {e}")
        return ""

def _is_possible_section_title(element, title_patterns):
    """ 요소가 지정된 패턴 중 하나와 일치하는 섹션 제목일 가능성이 있는지 확인 """
    if element is None or not hasattr(element, 'tag'): return None
    title_tags = {'title', 'h1', 'h2', 'h3', 'h4', 'p', 'b', 'strong'} # 검사 대상 태그
    tag_name = element.tag.lower() if isinstance(element.tag, str) else ''
    if tag_name not in title_tags: return None

    text = _get_text_content_lxml(element).strip()
    # 짧거나, 숫자만 있거나, 특정 단어(페이지 등)만 있는 경우 제외
    if not text or len(text) > 150 or len(re.findall(r'\w', text)) < 2 or text.isdigit() or "페이지" in text:
        return None

    # 패턴 매칭
    for pattern in title_patterns:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                # logger.debug(f"Potential title match: Pattern='{pattern}', Text='{text[:60]}...'")
                return text # 실제 찾은 텍스트 반환
        except Exception as re_e: logger.error(f"Regex error: {re_e}")
    return None

# --- 메인 XML 데이터 추출 함수 (섹션 단위 추출) ---
def extract_targeted_data_from_xml(
    xml_content_str: str | None,
    source_document_id: str,
    company_code: str,
    company_name: str,
    **kwargs
    ) -> list[dict]:
    """
    DART XML(HTML 파서로 처리)에서 사용자 지정 주요 섹션 제목을 기준으로,
    각 섹션의 전체 텍스트를 추출하여 딕셔너리 리스트로 반환합니다.
    """
    if not xml_content_str: logger.warning(f"XML content empty for {source_document_id}."); return []
    if not LXML_AVAILABLE: logger.error("lxml library not available."); return []

    extracted_sections = []
    logger.info(f"Starting SECTION-LEVEL XML parsing for: {source_document_id}")
    try:
        parser = etree.HTMLParser(encoding='utf-8', recover=True)
        root = etree.fromstring(xml_content_str.encode('utf-8'), parser=parser)
        if root is None: logger.error("Failed to parse XML/HTML root."); return []

        # --- 추출 대상 섹션 정의 (사용자 지정 기반) ---
        # 키: 내부 ID, 값: [ 대표 섹션명 (메타데이터용), [정규식 패턴] ]
        section_patterns_map = {
            "BUSINESS_CONTENT": ["II. 사업의 내용", [r"^[II]+\.\s*사업의\s*내용"]],
            # "BUSINESS_CONTENT" 하위 주요 섹션도 별도 추출 원하면 추가
            "RAW_MATERIALS": ["II-3. 원재료 관련", [r"\d+\.?\s*원재료"]], # 사업의 내용 하위
            "SALES_ORDERS": ["II-4. 매출 및 수주 관련", [r"\d+\.?\s*매출"]], # 사업의 내용 하위
            "CONTRACTS_RD": ["II-6. 주요계약 및 연구개발", [r"\d+\.?\s*주요\s*계약", r"\d+\.?\s*연구개발"]], # 사업의 내용 하위
            "AFFILIATES": ["IX. 계열회사 등에 관한 사항", [r"^[IX]+\.\s*계열회사"]],
            # 상세표는 내용 없을 수 있으므로 주의
            "APPENDIX_SUBSIDIARIES": ["XII-1. 연결대상 종속회사 현황", [r"1\.\s*연결대상\s*종속회사"]],
            "APPENDIX_AFFILIATES": ["XII-2. 계열회사 현황", [r"2\.\s*계열회사\s*현황"]],
        }

        body = root.find('.//body');
        if body is None: body = root

        current_section_title = "문서 시작" # 실제 찾은 제목으로 업데이트됨
        current_section_content_elements = [] # 현재 섹션의 lxml 요소 저장 리스트
        last_title_element = None # 마지막으로 찾은 제목 요소

        # body 내 모든 요소를 순회하며 섹션 구분 및 내용 추출
        for element in body.iter():
            # 요소가 주석이나 처리 지시문이면 건너뛰기
            if not isinstance(element.tag, str): continue

            matched_section_key = None
            title_text_found = None

            # 현재 요소가 새로운 섹션 제목인지 판별
            for section_key, (display_title, patterns) in section_patterns_map.items():
                match_text = _is_possible_section_title(element, patterns)
                if match_text:
                    # 더 구체적인 제목(예: 'II-3')이 이미 찾은 상위 제목(예: 'II.')과 관련 없을 때만 새 섹션으로 처리하는 로직 추가 가능
                    matched_section_key = section_key
                    title_text_found = match_text # 실제 찾은 제목 사용
                    break

            # 새로운 섹션 제목을 찾았다면
            if matched_section_key:
                # 이전 섹션 내용 처리 (요소 리스트 -> 텍스트 변환)
                if current_section_content_elements:
                    section_text = "\n".join(
                        _get_text_content_lxml(elem) for elem in current_section_content_elements
                        if elem is not None and elem.tag.lower() not in ['style', 'script'] # 스타일/스크립트 제외
                    ).strip()
                    # 내용이 충분히 있으면 저장
                    if len(section_text) > 20: # 길이 임계값 조정
                        extracted_sections.append({
                            "content": section_text,
                            "original_section": current_section_title
                        })
                        logger.debug(f"Saved previous section '{current_section_title[:60]}...' (Length: {len(section_text)})")

                # 새 섹션 정보 업데이트
                current_section_title = title_text_found
                current_section_content_elements = [] # 내용 초기화
                last_title_element = element # 이 제목 요소는 내용에 포함 안 함

            # 제목 요소가 아니면 현재 섹션 내용 요소로 추가
            elif element is not last_title_element:
                current_section_content_elements.append(element)

        # 마지막 섹션 내용 저장
        if current_section_content_elements:
            section_text = "\n".join(
                _get_text_content_lxml(elem) for elem in current_section_content_elements
                if elem is not None and elem.tag.lower() not in ['style', 'script']
            ).strip()
            if len(section_text) > 20:
                extracted_sections.append({
                    "content": section_text,
                    "original_section": current_section_title
                })
                logger.debug(f"Saved final section '{current_section_title[:60]}...' (Length: {len(section_text)})")

    except Exception as e:
        logger.error(f"Error in SECTION-LEVEL XML extraction ({source_document_id}): {e}", exc_info=True)
        return []

    logger.info(f"SECTION-LEVEL XML parsing finished for {source_document_id}. Extracted {len(extracted_sections)} sections.")
    return extracted_sections