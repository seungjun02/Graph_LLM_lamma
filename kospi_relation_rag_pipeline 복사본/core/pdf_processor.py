# core/pdf_processor.py

import PyPDF2
import re
import os
import logging
from langchain.docstore.document import Document

logger = logging.getLogger("KospiRAGPipeline")

# --- 핵심 키워드 정의 (사용자 지정 기준) ---
# 이 키워드들의 존재 유무로 경쟁사 비교 페이지를 식별
# 복합 키워드 처리: '&' 등을 고려하여 분리하거나 정규식 사용
COMPETITOR_PAGE_INDICATORS = [
    "투자의견",
    "Margin",         # "Margin & Growth"
    "Growth",         # "Margin & Growth"
    "주가수익률",
    "수익률 비교",
    "Price",          # "Price & Fundamentals"
    "Fundamentals"    # "Price & Fundamentals"
]
# 페이지 내에 아래 개수 이상의 핵심 키워드가 포함되어야 함
MIN_INDICATORS_THRESHOLD = 2 # 임계값 (조정 가능)

def count_page_indicators(text):
    """페이지 텍스트 내 경쟁사 페이지 핵심 키워드 개수 확인"""
    count = 0
    processed_text = text.lower() # 대소문자 무시
    found_indicators = set() # 동일 키워드 중복 카운트 방지

    # '&'를 포함하는 원본 키워드도 확인 (선택적)
    # if "margin & growth" in processed_text: found_indicators.add("Margin & Growth")
    # if "price & fundamentals" in processed_text: found_indicators.add("Price & Fundamentals")

    # 분리된/단일 키워드 확인
    for keyword in COMPETITOR_PAGE_INDICATORS:
        # 단어 경계를 고려한 정규식 매칭이 더 정확할 수 있음
        # 예: pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        # if re.search(pattern, processed_text):
        #     found_indicators.add(keyword)

        # 단순 포함 여부 확인 (현재 방식)
        if keyword.lower() in processed_text:
            found_indicators.add(keyword)

    # logger.debug(f"Found indicators: {found_indicators}") # 디버깅용
    return len(found_indicators) # 고유하게 찾은 키워드 개수 반환

# extract_text_from_pdf 함수 (이전과 동일)
def extract_text_from_pdf(pdf_path):
    """PDF 파일에서 페이지별 텍스트 추출"""
    pages_text = {}
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            num_pages = len(reader.pages)
            for i in range(num_pages):
                try:
                    page = reader.pages[i]
                    text = page.extract_text()
                    if text:
                        text = re.sub(r'\s+', ' ', text).strip()
                        pages_text[i + 1] = text
                except Exception as page_e:
                    logger.warning(f"Could not extract text from page {i+1} of {pdf_path}: {page_e}")
    except FileNotFoundError:
        logger.error(f"PDF file not found: {pdf_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to read PDF file {pdf_path}: {e}")
        return None
    return pages_text

def process_fnguide_pdf(pdf_path: str, company_code: str) -> list[Document]:
    """
    FnGuide PDF 처리 (사용자 지정 핵심 키워드 기반 필터링).
    핵심 키워드가 MIN_INDICATORS_THRESHOLD 개수 이상 포함된 페이지만 경쟁 컨텍스트로 처리.
    """
    docs = []
    if not os.path.exists(pdf_path):
        logger.error(f"FnGuide PDF not found: {pdf_path}")
        return docs

    pages_content = extract_text_from_pdf(pdf_path)
    if not pages_content:
        return docs

    logger.info(f"Processing FnGuide PDF for {company_code} ({len(pages_content)} pages): {pdf_path}")

    processed_page_nums = set() # 중복 처리 방지용

    for page_num, page_text in pages_content.items():
        if page_num in processed_page_nums or not page_text or len(page_text) < 50:
            continue

        # --- 경쟁 관계 페이지 식별 (사용자 지정 키워드 기준) ---
        indicator_count = count_page_indicators(page_text)

        # 핵심 지표 키워드가 임계값 이상 포함된 경우
        if indicator_count >= MIN_INDICATORS_THRESHOLD:
            logger.info(f"Page {page_num} identified as Competitor Page for {company_code} (Indicators found: {indicator_count})")
            metadata = {
                'company_code': company_code,
                'document_type': 'FnGuide_PDF (Competition Page)', # 문서 타입 명시
                'potential_relation_type': 'competition', # 'competition' 태그 추가
                'section': f'Competitor Metrics Page {page_num}', # 페이지 정보
                'source': pdf_path,
                'report_date': 'unknown' # TODO: 날짜 추출
            }
            # 페이지 전체 내용을 content로 사용
            docs.append(Document(page_content=page_text, metadata=metadata))
            processed_page_nums.add(page_num) # 처리된 페이지로 기록
            continue # 다음 페이지로

        # --- (선택적) 다른 정보 추출 로직 ---
        # ... (예: 소유구조, 요약 등)

    if not docs:
         logger.warning(f"No pages meeting the competitor criteria found in FnGuide PDF for {company_code}.")
    else:
        logger.info(f"Finished processing FnGuide PDF for {company_code}. Generated {len(docs)} competition documents.")

    return docs