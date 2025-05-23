### 10. core/matrix_builder.py (수정됨: scipy.sparse 대신 numpy 기능 사용)

import numpy as np
# import scipy.sparse as sp # scipy.sparse 임포트 제거
from config import logger # config.py 가 동일 경로 또는 sys.path에 있어야 함

# build_adjacency_matrix 함수의 반환 타입 힌트를 numpy 배열로 변경
def build_adjacency_matrix(relationships: dict) -> np.ndarray:
    """
    LLM에서 추출된 관계 정보를 기반으로 인접 행렬 (NumPy 배열)을 생성하는 함수
    relationships: {'company_a': ..., 'company_b': ..., 'relationships': [ { "type": ..., "strength": ... , "evidence": [...] }, ... ]}
    이 예시는 간단히 두 기업 간 단일 관계 강도를 수치화해 인접 행렬에 반영합니다.
    """
    # 예시: 100개 기업 (실제 매핑 정보 필요), 여기서는 임의 크기 100x100 행렬로 생성
    num_nodes = 100 # 실제 노드 수로 변경 필요
    matrix = np.zeros((num_nodes, num_nodes), dtype=np.float32) # 데이터 타입 명시 (예: float32)

    # --- 실제 관계 데이터로 matrix 채우는 로직 필요 ---
    # 예시: company_a -> company_b 관계 (인덱스 매핑 필요)
    # if relationships:
    #     # 여기에 relationships 딕셔너리를 파싱하여 matrix[idx_a, idx_b] = value 형태로 채우는 코드 추가
    #     # 예: strength = relationships['relationships'][0]['strength'] # 실제 구조에 맞게 파싱
    #     # matrix[company_to_index[relationships['company_a']], company_to_index[relationships['company_b']]] = strength
    #     pass # 실제 구현 필요
    # ---------------------------------------------

    logger.info(f"NumPy 인접 행렬 생성 완료 (Shape: {matrix.shape}) - 실제 매핑 및 계산 필요")
    # scipy.sparse 변환 없이 NumPy 배열 그대로 반환
    return matrix

# save_matrix 함수의 입력 타입 힌트를 numpy 배열로 변경
def save_matrix(matrix: np.ndarray, file_path: str):
    """
    인접 행렬 (NumPy 배열)을 압축된 .npz 파일로 저장하는 함수
    """
    if not isinstance(matrix, np.ndarray):
        logger.error(f"Invalid input: Expected a NumPy array, but got {type(matrix)}")
        return

    # 파일 확장자가 .npz가 아니면 추가 (savez_compressed는 자동으로 추가하지 않음)
    if not file_path.endswith('.npz'):
        file_path += '.npz'

    try:
        # numpy.savez_compressed 사용하여 NumPy 배열 저장 (압축된 .npz 형식)
        # 키워드 인자(예: 'adjacency_matrix')를 사용하여 배열 저장 권장
        np.savez_compressed(file_path, adjacency_matrix=matrix)
        logger.info(f"NumPy 인접 행렬 저장 완료: {file_path}")
    except Exception as e:
        logger.error(f"NumPy 인접 행렬 저장 오류 ({file_path}): {e}")