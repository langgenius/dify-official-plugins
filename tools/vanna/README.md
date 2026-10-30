# Overview
Vanna.ai is an innovative AI-driven platform designed to simplify the interaction between users and complex SQL databases. 

# Configure
## Get API Key
1. Create an account and login to Vanna.ai.
2. Copy API key from API Keys.

## Configure Vanna.AI tool
1. Install Vanna.AI from Marketplace. 
![](./_assets/vanna_install.png)
2. Add Vanna.AI node to your workflow.
3. Fill in the Vanna.AI API key.
4. Fill in the database configurations.
![](./_assets/vanna_configure.png)

## Database connections

SQLite and DuckDB accept an existing local database file or an HTTP(S) download URL.
DuckDB also accepts `:memory:`, `md:` and `motherduck:` connections.
For Microsoft SQL Server, enter an ODBC connection string in URL/Host/DSN.
The plugin runtime must have unixODBC and the corresponding SQL Server ODBC driver installed.
