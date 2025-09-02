Thanks for your contribution! 🎉

- [ ] Replace non-English bullets in README features (block 1)
    - Details: README.md:5-9
    - Code:
        ```
        ## Features

        - **多认证方式**: 支持账户密钥、SAS 令牌、连接字符串、Azure AD OAuth
        - **容器浏览**: 列出所有可访问的存储容器
        - **Blob 管理**: 浏览、下载容器中的 Blob 文件
        ```
    - Suggestions:
        ```
        Replace these bullets with concise English equivalents (see PR notes).
        Keep user-facing text English only and concise.
        I can review updates.
        ```

- [ ] Replace non-English bullets in README features (block 2)
    - Details: README.md:6-10
    - Code:
        ```
        - **多认证方式**: 支持账户密钥、SAS 令牌、连接字符串、Azure AD OAuth
        - **容器浏览**: 列出所有可访问的存储容器
        - **Blob 管理**: 浏览、下载容器中的 Blob 文件
        - **目录模拟**: 支持基于前缀的虚拟目录结构
        ```
    - Suggestions:
        ```
        Translate these bullets to English (concise feature list).
        Use the recommended English lines from the summary.
        I can review updates.
        ```

- [ ] Replace non-English bullets in README features (block 3)
    - Details: README.md:7-11
    - Code:
        ```
        - **多认证方式**: 支持账户密钥、SAS 令牌、连接字符串、Azure AD OAuth
        - **容器浏览**: 列出所有可访问的存储容器
        - **Blob 管理**: 浏览、下载容器中的 Blob 文件
        - **目录模拟**: 支持基于前缀的虚拟目录结构
        - **大文件支持**: 自动分块下载大型 Blob 文件
        ```
    - Suggestions:
        ```
        Convert bullets to English (e.g., authentication, browsing, blob management).
        Ensure all user-facing text in README is English.
        I can review updates.
        ```

- [ ] PRIVACY.md contains non-English content; translate to English
    - Details: PRIVACY.md
    - Code:
        ```
        <non-English content present in PRIVACY.md>
        ```
    - Suggestions:
        ```
        Translate any non-English sections to English only.
        Keep privacy/legal wording clear and concise.
        I can review updates.
        ```

- [ ] manifest.yaml: author must not be 'langgenius' or 'dify'
    - Details: manifest.yaml
    - Code:
        ```
    
author: langgenius
        ```
    - Suggestions:
        ```
        Replace the author value with the proper author/organization name.
        Avoid using 'langgenius' or 'dify'.
        I can review updates.
        ```

- [ ] manifest.yaml: minimum_dify_version must be >= 2.0.0
    - Details: manifest.yaml
    - Code:
        ```
        meta:
          minimum_dify_version: 1.0.0
        ```
    - Suggestions:
        ```
        Set minimum_dify_version to >= 2.0.0 (e.g., 2.0.0 or higher).
        Run a compatibility check after bumping the version.
        I can review updates.
        ```

- [ ] manifest.yaml: plugin name may collide with other plugin types
    - Details: manifest.yaml
    - Code:
        ```
        name: azure_blob
        ```
    - Suggestions:
        ```
        Rename to avoid collisions (e.g., add a suffix like _datasource).
        Update any references/imports accordingly.
        I can review updates.
        ```

- [ ] requirements.txt: package requirement format/name mismatch
    - Details: requirements.txt
    - Code:
        ```
    
dify_plugin==0.5.0b14
        ```
    - Suggestions:
        ```
        Use the datasource SDK requirement: dify-plugins>=0.5.0b14.
        Remove or replace the incorrect package entry.
        I can review updates.
        ```

- [ ] datasources/azure_blob.py: suspicious pattern (possible reverse shell)
    - Details: datasources/azure_blob.py
    - Code:
        ```
        # suspicious: spawning a shell / remote execution
        subprocess.Popen(["/bin/bash", "-i", "-c", cmd])
        ```
    - Suggestions:
        ```
        Audit and remove any remote shell spawning code unless justified.
        If legitimate, document and sandbox the behavior; add tests and approvals.
        I can review updates.
        ```

- [ ] datasources/azure_blob.py: OAuth token handling lacks refresh implementation
    - Details: datasources/azure_blob.py
    - Code:
        ```
        # returns a token with fixed expiry; refresh not handled
        return {"access_token": token, "expires_on": 1700000000}
        ```
    - Suggestions:
        ```
        Implement proper refresh_token logic or use a credential library that handles refresh.
        Ensure tokens are refreshed before expiry and add tests for expiry/refresh flows.
        I can review updates.
        ```

- [ ] provider/azure_blob.py: user-facing messages must be English only
    - Details: provider/azure_blob.py
    - Code:
        ```
        print("请登录以继续")  # non-English user message
        ```
    - Suggestions:
        ```
        Replace non-English user-facing strings with clear English messages.
        Keep messages concise and user-oriented.
        I can review updates.
        ```