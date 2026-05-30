# VPS Git Permission Audit

- current_user: `deploy`
- repo owner/group before fix: `lpbot:lpbot` on `.git`, `.git/index`, `.git/refs`, `.git/objects`
- `.git/FETCH_HEAD` before fix: missing, but `git fetch` failed while trying to create it
- original git fetch error: `cannot open .git/FETCH_HEAD: Permission denied`
- root_cause: `wrong_owner`

修复后 `.git` 目录已经改成 `deploy:deploy`，权限层面的 `FETCH_HEAD` 阻断已消失。
新的阻断变成远端认证：`Repository not found / Could not read from remote repository`。这不是本地文件权限问题。
