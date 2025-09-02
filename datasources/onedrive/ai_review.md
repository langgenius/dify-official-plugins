Thanks for your contribution! 🎉

- [ ] Add PRIVACY.md with comprehensive data handling info
    - Details: PRIVACY.md
    - Code:
        ```
        # PRIVACY.md
        # (file missing)
        ```
    - Suggestions:
        ```
        Include data types collected, retention, sharing, user rights, contact
        ```

- [ ] Review and remove suspicious command/remote-shell patterns
    - Details: datasources/onedrive.py
    - Code:
        ```
        # suspicious use of subprocess/os.system or exec with external input
        # e.g. subprocess.Popen(...)
        ```
    - Suggestions:
        ```
        Replace unsafe subprocess/exec usage; validate inputs
        Limit functionality to safe APIs and add tests
        ```

- [ ] Update author field to a permissible value (not 'langgenius' or 'dify')
    - Details: manifest.yaml
    - Code:
        ```
        meta:
          author: langgenius
        ```
    - Suggestions:
        ```
        Use an appropriate org/team or individual name
        Avoid reserved/vendor names
        ```

- [ ] Add README.md with overview, setup, and usage
    - Details: README.md
    - Code:
        ```
        # README.md
        # (file missing)
        ```
    - Suggestions:
        ```
        Add overview, install/setup, env vars, usage examples, limits/troubleshooting
        ```

- [ ] Remove client_secret from returned credentials object
    - Details: provider/onedrive.py
    - Code:
        ```
        return DatasourceOAuthCredentials(
            name=user.get("displayName") or user.get("userPrincipalName"),
            avatar_url=None,
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "client_id": system_credentials["client_id"],
                "client_secret": system_credentials["client_secret"],
                "user_email": user.get("userPrincipalName"),
            },
        )
        ```
    - Suggestions:
        ```
        Keep client_secret only in server-side config; remove from credentials dict
        Expose only tokens/identifiers needed at runtime
        ```

- [ ] Bump minimum_dify_version to >= 2.0.0
    - Details: manifest.yaml
    - Code:
        ```
        meta:
          ...
          minimum_dify_version: 1.0.0
        ```
    - Suggestions:
        ```
        Set minimum_dify_version: 2.0.0 or higher
        Run compatibility tests after the bump
        ```

- [ ] Use the correct SDK requirement and avoid incorrect pinning
    - Details: requirements.txt
    - Code:
        ```
        dify_plugin==0.5.0b14
        ```
    - Suggestions:
        ```
        Replace with: dify-plugins>=0.5.0b14
        Avoid strict pinning unless necessary
        ```

- [ ] Rename datasource identity to avoid collisions (avoid plain 'onedrive')
    - Details: provider/onedrive.yaml
    - Code:
        ```
        identity: onedrive
        ```
    - Suggestions:
        ```
        Use 'onedrive_datasource' or similar unique name
        Update references in code/manifest accordingly
        ```

I can review updates once these changes are pushed.