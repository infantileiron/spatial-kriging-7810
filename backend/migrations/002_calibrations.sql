-- 分区均值联合校正：每次提交保留一条版本记录。
-- applied=当前通过；superseded=曾经通过并被新版本替换；failed=校验/求解失败，旧版本继续生效。
-- 全部校正数值保存在 JSON payload（float64），不新增浮点列；原始克里金结果不做修改。
CREATE TABLE IF NOT EXISTS calibrations (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  created_at DATETIME NOT NULL,
  run_id VARCHAR(36) NOT NULL,
  version INTEGER NOT NULL,
  state VARCHAR(20) NOT NULL,
  payload JSON NOT NULL,
  error TEXT NOT NULL,
  conflict_zones JSON NOT NULL,
  input_sha256 VARCHAR(64) NOT NULL,
  actor VARCHAR(160) NOT NULL,
  CONSTRAINT fk_calibration_run FOREIGN KEY (run_id) REFERENCES runs (id),
  CONSTRAINT uq_calibration_run_version UNIQUE (run_id, version),
  INDEX ix_calibration_run_state (run_id, state)
);
