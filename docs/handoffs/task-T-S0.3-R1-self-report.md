# T-S0.3-R1 自报（一句话；不作数，以大统领实测为准）

做了什么：`db.py` 加 `_heal_missing_columns`（create_all 后对 SQLite 幂等 ALTER ADD 缺失列）并配旧库补齐单测，冒烟脚本 cwd 改仓库根并新增 `--database-url`；删误建 `app/backend/data/`；用仓库根旧库重跑冒烟 `uploading → transcribing → done`（exit 0）。

跑了什么命令/结果：`pytest app/backend/tests -q` = 24 passed；`ruff check app/backend tests/e2e/smoke_main_chain.py` = All checks passed；`.venv/bin/python tests/e2e/smoke_main_chain.py --database-url sqlite:////home/houmo/meng/MengPsyAssit/data/app.db` = PASS（segments=11, speakers=[P,T]）。

修复前后旧库实测对比（PRAGMA table_info(sessions)）：
- 补列前：`['id','user_id','client_id','mode','status','started_at','duration_sec','audio_path']`
- 补列后：`['id','user_id','client_id','mode','status','started_at','duration_sec','audio_path','cleaned_text']`；`users` dev 行仍在（[(1,'dev')]）。
