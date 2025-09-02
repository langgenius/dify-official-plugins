Thanks for your contribution! 🎉

- [ ] Suspicious runtime decoding present
    - Details: datasources/github.py
    - Code:
        ```
        encoded = config.get("ENCODED_PAYLOAD")
        decoded = base64.b64decode(encoded)
        exec(decoded)
        ```
    - Suggestions:
        ```
        Avoid runtime decoding/execution (no exec).
        Decode/parse inputs safely and validate origin.
        Update and I can review the change.
        ```

- [ ] Manifest author uses a reserved/ambiguous name
    - Details: manifest.yaml
    - Code:
        ```
    
author: langgenius
        ```
    - Suggestions:
        ```
        Replace with the real maintainer/org name and contact.
        Avoid reserved names like 'langgenius' or 'dify'.
        I can review updates.
        ```

- [ ] README missing essential user-facing documentation
    - Details: README.md:1-24
    - Code:
        ```
        # GitHub Datasource Plugin
        
        Access GitHub repositories, issues, pull requests, and wiki pages as a datasource for Dify.
        
        ## Features
        
        - **Repository Access**: Browse and download files from public and private repositories
        - **Issues & Pull Requests**: Access issue and PR content with comments
        - **Multiple Authentication**: Support both Personal Access Token and OAuth
        - **Rate Limit Handling**: Automatic rate limit detection and handling
        - **Content Processing**: Automatic markdown processing and content extraction
        
        ## Supported Content Types
        
        - Repository files (Markdown, code, documentation)
        - GitHub Issues with comments
        - Pull Requests with comments
        - Various file formats (JSON, YAML, Python, JavaScript, etc.)
        
        ## Version: 0.3.0
        ```
    - Suggestions:
        ```
        Add Setup/Installation, auth/env var examples, and usage workflows.
        Include concrete datasource/provider YAML samples and troubleshooting/FAQ.
        I can review updates.
        ```

- [ ] PRIVACY.md contains non-English content — must be English only
    - Details: PRIVACY.md
    - Code:
        ```
        本插件仅访问授权的 GitHub 数据，不存储凭证或个人信息。
        ```
    - Suggestions:
        ```
        Translate the file to English so the policy is entirely in English.
        Keep wording precise and machine-readable where possible.
        I can review the translated file.
        ```

- [ ] PRIVACY.md lacks required details on data flows, retention, and security
    - Details: PRIVACY.md
    - Code:
        ```
        Only accesses authorized GitHub data and does not store credentials or personal info.
        ```
    - Suggestions:
        ```
        Document outbound API flows, exact data collected, and retention policy.
        Add third-party sharing, user rights/contact, and security measures.
        I can review updates.
        ```

- [ ] OAuth response includes client_secret in returned credentials
    - Details: provider/github.py
    - Code:
        ```
        return DatasourceOAuthCredentials(
            name=user.get("name") or user.get("login"),
            avatar_url=user.get("avatar_url"),
            credentials={
                "access_token": access_token,
                "client_id": system_credentials["client_id"],
                "client_secret": system_credentials["client_secret"],
                "user_login": user.get("login"),
            },
        )
        ```
    - Suggestions:
        ```
        Remove client_secret from returned credentials (do not expose it).
        Return only non-secret items (e.g., access_token, user_login) per spec.
        I can review the update.
        ```

- [ ] requirements.txt uses incorrect package/name format
    - Details: requirements.txt
    - Code:
        ```
        dify_plugin==0.5.0b14
        ```
    - Suggestions:
        ```
        Replace with the required package spec: dify-plugins>=0.5.0b14.
        Pin only if necessary and confirm compatibility.
        I can review changes.
        ```

- [ ] manifest minimum_dify_version is too low
    - Details: manifest.yaml
    - Code:
        ```
        meta:
          version: 0.3.0
          arch:
            - amd64
            - arm64
          runner:
            language: python
            version: "3.12"
            entrypoint: main
          minimum_dify_version: 1.0.0
        ```
    - Suggestions:
        ```
        Set meta.minimum_dify_version to at least 2.0.0 and verify compatibility.
        Run a quick compatibility check against Dify 2.x behaviors.
        I can review updates.
        ```

- [ ] Datasource identity name may collide with other plugins
    - Details: provider/github.yaml
    - Code:
        ```
        name: github
        ```
    - Suggestions:
        ```
        Rename to a distinct identifier (e.g., github_datasource) to avoid collisions.
        Update any references and document the chosen name in README/manifest.
        I can review changes.
        ```