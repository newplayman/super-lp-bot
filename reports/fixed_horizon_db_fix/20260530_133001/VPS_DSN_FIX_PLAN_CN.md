# VPS DSN Fix Plan

- selected_plan: `方案 1：已有安全 env file`
- source_of_truth: systemd `EnvironmentFile` chain for `lpbot-shadow.service`
- action_taken: generated local non-git `.runtime.shadow.env` inside VPS workspace
- file_mode: `600`
- file_owner: `deploy:deploy`
- secret_leak: no

说明：不是把 secret 写入 Git，也不是把 DSN 明文写入报告；只是把 systemd 已有变量链路收敛成当前 workspace 可复用的只读 runtime env。
