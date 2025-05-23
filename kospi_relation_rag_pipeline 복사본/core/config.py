# core/config.py (Simplified for Colab Notebook)

import os
import logging
import sys

# --- 재시도 설정 (dart_utils에서 사용) ---
RETRY_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 5

# --- DART 관련 설정 (dart_utils에서 사용) ---
# 처리 대상 보고서 코드 (사업보고서, 반기보고서, 분기보고서, 1Q보고서)
TARGET_REPORT_CODES = ['11011', '11012', '11013', '11014']

# --- 로거 인스턴스 생성 ---
# 다른 모듈(dart_utils, matrix_builder)에서 이 로거를 가져다 사용할 수 있도록 함.
# 로거의 상세 설정(핸들러 추가, 레벨 설정 등)은 메인 노트북 Cell 1에서 수행함.
logger = logging.getLogger("KospiRAGPipeline") # 파이프라인 전체에서 사용할 로거 이름 지정

# 기본 핸들러가 없을 경우에만 NullHandler 추가 (핸들러 중복 방지 및 경고 방지)
if not logger.hasHandlers():
    logger.setLevel(logging.INFO) # 기본 레벨 설정 (노트북에서 변경 가능)
    logger.addHandler(logging.NullHandler())

# --- 불필요한 설정 제거 ---
# DART_API_KEY: 노트북 Cell 1에서 직접 설정 및 dart_fss.set_api_key() 호출
# 경로 설정 (BASE_DIR, DATA_DIR 등): 노트북 Cell 1에서 DRIVE_MOUNT_PATH 기준으로 설정
# Azure 설정: 현재 파이프라인에서 사용 안 함
# RAG 파라미터 (TARGET_YEAR, CHUNK_SIZE 등): 노트북 Cell 1에서 설정
# STRENGTH_MAP: 현재 파이프라인에서 사용 안 함

# --- config 모듈 로드 확인용 (선택적) ---
# logger.debug("Simplified config.py loaded.")