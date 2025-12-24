import json
from tools import convert_student_data

with open("sp_agent/raw_data/TT_feature_data_api_fin.json", "r", encoding="utf-8") as f:
    feature_json = f.read()

with open("sp_agent/raw_data/TT_종합분석_data.json", "r", encoding="utf-8") as f:
    raw_json = f.read()

summary = convert_student_data(feature_json, raw_json)

# 전체 구조 확인
print(json.dumps(summary, ensure_ascii=False, indent=2))

# 필요한 key 들만 빠르게 체크해보기
for key in [
    "exam_summary",
    "subjects_current",
    "subjects_scores_trend",
    "readi_activity",
    "readi_scores",
    "reading_overview",
    "Absence_overview",
]:
    print(key, "=>", "OK" if key in summary else "MISSING")