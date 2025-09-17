# Plugin Dify Zoom

**Autor**: langgenius
**Versão**: 0.1.0
**Tipo**: tool

## Introdução

Este plugin se integra com a plataforma de videoconferência Zoom, fornecendo recursos abrangentes de gerenciamento de reuniões. Ele permite a criação, recuperação, atualização e exclusão automatizada de reuniões do Zoom através das plataformas Dify. O plugin suporta vários tipos de reunião, incluindo reuniões instantâneas, agendadas e recorrentes com opções de configuração avançadas.

## Configuração

1. Crie sua aplicação no [Zoom App Marketplace](https://marketplace.zoom.us/develop/create).

   <img src="_assets/create_app.png" alt="Create App" width="300"/>

   *Criar uma nova aplicação Zoom*

2. Escolha **General App** como o tipo de aplicação.

3. Configure sua aplicação conforme segue:
    - **App name**: Dify Zoom Plugin
    - **Choose your app type**: Server-to-Server OAuth
    - **Would you like to publish this app on Zoom App Marketplace?**: No (para uso privado)

4. Na seção **OAuth**:
    - **OAuth Redirect URL**: Defina o URI de redirecionamento apropriado:
        - Para usuários SaaS (cloud.dify.ai): `https://cloud.dify.ai/console/api/oauth/plugin/langgenius/zoom/zoom/tool/callback`
        - Para usuários auto-hospedados: `http://<YOUR_LOCALHOST_CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/zoom/zoom/tool/callback`
    - **OAuth allow list**: Adicione seu domínio se necessário

5. Copie seu **Client ID** e **Client Secret** da seção App Credentials.

6. Escolha os Escopos conforme segue:

   <img src="_assets/add_scope.png" alt="Add Scope" width="300"/>

   *Configurar escopos de permissão OAuth*

7. Adicionar usuário de teste:

   <img src="_assets/add_test_user.png" alt="Add Test User" width="300"/>

   *Adicionar usuários de teste à sua aplicação*

8. Configure o plugin no Dify:
    - Preencha os campos **Client ID** e **Client Secret** com os valores da sua aplicação Zoom
    - Certifique-se de que o URI de redirecionamento corresponde ao que você configurou no Zoom App Marketplace
    - Clique em `Save and authorize` para iniciar o fluxo OAuth e conceder permissões

9. Complete o processo de autorização OAuth fazendo login na sua conta Zoom e aprovando as permissões da aplicação.

## Demonstração de Uso

<img src="_assets/result.png" alt="Plugin Result" width="300"/>

*Demonstração de integração e uso do plugin*

## Descrições das Ferramentas

### zoom_create_meeting
Criar uma nova reunião Zoom com configurações personalizáveis e obter links da reunião.

**Parâmetros:**
- **topic** (string, obrigatório): O tópico ou título da reunião
- **type** (select, opcional): Tipo de reunião - instantânea (1), agendada (2), recorrente sem horário fixo (3), ou recorrente com horário fixo (8). Padrão: agendada (2)
- **start_time** (string, opcional): Horário de início da reunião no formato ISO 8601 (ex.: 2024-12-25T10:00:00Z)
- **duration** (number, opcional): Duração da reunião em minutos (1-1440). Padrão: 60
- **password** (string, opcional): Senha opcional para proteger a reunião
- **waiting_room** (boolean, opcional): Habilitar sala de espera para participantes. Padrão: true
- **join_before_host** (boolean, opcional): Permitir que participantes entrem antes da chegada do anfitrião. Padrão: false
- **mute_upon_entry** (boolean, opcional): Silenciar automaticamente participantes quando entrarem. Padrão: true
- **auto_recording** (select, opcional): Configuração de gravação automática - nenhuma, local, ou nuvem. Padrão: nenhuma
- **timezone** (string, opcional): Fuso horário para a reunião. Padrão: UTC
- **agenda** (string, opcional): Agenda da reunião ou descrição detalhada

**Retorna:** ID da reunião, URL de entrada, URL de início, senha e detalhes da reunião.

### zoom_get_meeting
Recuperar informações abrangentes sobre uma reunião Zoom pelo ID da reunião.

**Parâmetros:**
- **meeting_id** (string, obrigatório): O identificador único da reunião Zoom
- **occurrence_id** (string, opcional): ID de ocorrência para reuniões recorrentes
- **show_previous_occurrences** (boolean, opcional): Incluir ocorrências anteriores para reuniões recorrentes. Padrão: false

**Retorna:** Informações completas da reunião incluindo configurações, URLs, detalhes do anfitrião e dados de ocorrência para reuniões recorrentes.

### zoom_list_meetings
Listar todas as reuniões Zoom para o usuário autenticado com opções de filtragem avançadas.

**Parâmetros:**
- **type** (select, opcional): Filtro de tipo de reunião - agendada, ao vivo, próximas, reuniões_próximas, ou reuniões_anteriores. Padrão: agendada
- **page_size** (number, opcional): Número de reuniões por página (1-300). Padrão: 30
- **page_number** (number, opcional): Número da página a recuperar (inicia em 1). Padrão: 1
- **from_date** (string, opcional): Data de início para filtrar reuniões (formato YYYY-MM-DD)
- **to_date** (string, opcional): Data de fim para filtrar reuniões (formato YYYY-MM-DD)

**Retorna:** Lista de reuniões com informações de paginação e filtros aplicados.

### zoom_update_meeting
Atualizar uma reunião Zoom existente com novas configurações.

**Parâmetros:**
- **meeting_id** (string, obrigatório): O identificador único da reunião Zoom a atualizar
- **topic** (string, opcional): Novo tópico ou título da reunião
- **type** (select, opcional): Novo tipo de reunião
- **start_time** (string, opcional): Novo horário de início no formato ISO 8601
- **duration** (number, opcional): Nova duração em minutos (1-1440)
- **timezone** (string, opcional): Novo identificador de fuso horário
- **password** (string, opcional): Nova senha da reunião
- **agenda** (string, opcional): Nova agenda ou descrição da reunião
- **waiting_room** (boolean, opcional): Atualizar configuração da sala de espera
- **join_before_host** (boolean, opcional): Atualizar configuração de entrada antes do anfitrião
- **mute_upon_entry** (boolean, opcional): Atualizar configuração de silenciar ao entrar
- **auto_recording** (select, opcional): Nova configuração de gravação automática
- **occurrence_id** (string, opcional): ID de ocorrência para atualizar uma ocorrência específica de uma reunião recorrente

**Retorna:** Status de sucesso, informações da reunião atualizada e detalhes das alterações feitas.

### zoom_delete_meeting
Excluir uma reunião Zoom pelo ID da reunião com opções de notificação.

**Parâmetros:**
- **meeting_id** (string, obrigatório): O identificador único da reunião Zoom a excluir
- **occurrence_id** (string, opcional): ID de ocorrência para excluir uma ocorrência específica de uma reunião recorrente
- **schedule_for_reminder** (boolean, opcional): Enviar email de lembrete aos inscritos sobre o cancelamento. Padrão: false
- **cancel_meeting_reminder** (boolean, opcional): Enviar emails de cancelamento aos inscritos e palestrantes. Padrão: false

**Retorna:** Status de sucesso, informações da reunião excluída e tipo de exclusão (reunião inteira ou ocorrência específica).

## PRIVACIDADE

Por favor, consulte a [Política de Privacidade](PRIVACY.md) para informações sobre como seus dados são tratados ao usar este plugin.

Última atualização: Agosto 2025