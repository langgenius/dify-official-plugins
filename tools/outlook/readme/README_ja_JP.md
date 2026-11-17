# Outlook

Microsoft Graph 経由で Microsoft Outlook と連携する Dify プラグインです。**メールとカレンダー**に対応し、メールの読み取り・送信・整理と、カレンダーの予定の管理ができます。

**バージョン:** 1.0.0

## 認証方法を選ぶ

| 方法 | ツールが使うメールボックス | 向いている用途 |
|---|---|---|
| **OAuth** | Dify のコンソールでサインインした 1 人のメールボックス。ツールを使う全員で共有します | 決まった 1 つのメールボックスを扱うワークフローやアプリ |
| **サービス プリンシパル**（0.7.0） | 指定したメールボックスに、アプリ自身としてアクセスします。ユーザーのサインインはありません | 共有メールボックスやサービス用メールボックスの自動化 |
| **ユーザーごとにサインイン**（1.0.0） | エージェントとチャットしている本人のメールボックス。各ユーザーが自分の Microsoft アカウントで一度サインインします | 多くの人が使うチャット エージェント（「今日の予定は？」） |

3 つとも同じ Microsoft Entra のアプリ登録（下の手順 1）を使い、併用できます。プラグインに複数の認証を追加し、エージェントやワークフローのノードごとに 1 つ選びます。

## 機能

### メール
- **List Messages**: 受信トレイのメールを一覧表示します。
- **Get Message**: ID を指定してメールの詳細（添付ファイルの ID を含む）を取得します。
- **Download Attachment**: メールの添付ファイルをダウンロードします（`message_id` と `attachment_id` が必要）。Dify が公開 HTTPS URL でファイルを提供します。
- **Send Message**: Outlook からメールを送信します。添付ファイルも付けられます。
- **Send Draft**: 下書きを送信します（Draft Email が返す下書き ID が必要）。
- **Draft Email**: 下書きを作成します。
- **List Draft Emails**: 下書きを一覧表示します。
- **Add Attachment to Draft**: 下書きに添付ファイルを追加します。
- **Prioritize Email**: メールの重要度を設定します。
- **Flag Message**: メールにフラグを付ける、または外します。

### カレンダー
- **List Calendars**: カレンダーを一覧表示します。
- **List Events**: 今後の予定を一覧表示します。カレンダーを指定することもできます。
- **Search Events**: キーワードや日付範囲で予定を検索します。
- List Events と Search Events は、各予定の場所とオンライン会議の参加リンク（Teams、または招待本文にある Zoom / Google Meet / Webex のリンク）も表示するので、エージェントが予定を 1 件ずつ開かなくてもオンライン会議かどうかがわかります（1.0.0）。
- **List Calendar Groups**（0.7.0）: *My Calendars* や *People's calendars* などのカレンダー グループを一覧表示します。共有されたカレンダーは通常、後者に入っています。
- **カレンダー グループと共有カレンダー**（0.7.0）: List Calendars、List Events、Search Events に **Calendar Group ID** を指定すると、グループ内のすべてのカレンダーが対象になり、各予定にカレンダーと所有者が付きます。`Calendars.Read.Shared` が必要です。
- **Get Schedule**（0.7.0）: 指定した時間帯の空き時間を、メールアドレスやカレンダー グループで調べます。カレンダーを共有していなくても組織内の誰でも調べられます。件名は閲覧権限がある予定だけに表示されます。
- **Create Event**: 会議や予定を作成します（出席者、場所、Teams オンライン会議）。
- **Get Event**、**Update Event**、**Delete Event**。

### アカウント
- **Sign Out of Outlook**（`outlook_sign_out`、1.0.0）: 「ユーザーごとにサインイン」でのみ使えます。現在のユーザーの Outlook のサインインを削除し、アカウントを切り替えられるようにします。ほかのプラグイン（Teams など）のサインインはそのままです。

## 手順 1: Microsoft Entra ID にアプリを登録する

どの方法でもアプリ登録が必要です。テナントでアプリを登録し、管理者の同意を付与できるアカウントを使ってください。

1. [Microsoft Entra 管理センター](https://entra.microsoft.com) → **App registrations** → **New registration** を開きます。

   ![New registration](../_assets/entra-new-registration.png)

2. 名前（例: `Dify Outlook`）を入力し、**Single tenant only** のままにします。**Redirect URI** は **Web** を選びます。OAuth を使う場合は Dify に表示されるコールバック URL（[OAuth](#oauth) を参照）を入力し、使わない場合は空のままにして後で追加します。**Register** をクリックします。

   ![Register an application](../_assets/entra-register-form.png)

3. アプリの **Overview** で **Application (client) ID** と **Directory (tenant) ID** をコピーします。

   ![クライアント ID とテナント ID](../_assets/entra-overview-ids.png)

4. **API permissions** → **Add a permission** → **Microsoft Graph** で、使う方法に必要なアクセス許可を追加します。

   | アクセス許可 | 種類 | 必要な方法 |
   |---|---|---|
   | `Mail.Read`、`Mail.ReadWrite`、`Mail.Send` | 委任（Delegated） | OAuth、ユーザーごとにサインイン |
   | `Calendars.ReadWrite` | 委任 | OAuth、ユーザーごとにサインイン |
   | `Calendars.Read.Shared` | 委任 | OAuth、ユーザーごとにサインイン（共有カレンダー、Get Schedule） |
   | `offline_access` | 委任 | OAuth、ユーザーごとにサインイン（サインイン状態の維持） |
   | `Mail.ReadWrite`、`Mail.Send`、`Calendars.ReadWrite` | アプリケーション（Application） | サービス プリンシパル |

   新しいアプリに既定で付いている `User.Read` はそのままで構いません。

5. **Grant admin consent for \<組織名\>** をクリックし、**Yes** で確定します。サービス プリンシパルでは必須です。「ユーザーごとにサインイン」でも強く推奨します。ユーザーに同意画面が表示されなくなり、ブラウザーで Microsoft にサインイン済みならワンクリックでサインインできます。

   ![管理者の同意を付与](../_assets/entra-grant-consent.png)

6. **Certificates & secrets** → **Client secrets** で **New client secret** をクリックします。**Value** はすぐにコピーしてください（一度しか表示されません）。**Secret ID** はシークレットではありません。

   ![New client secret](../_assets/entra-client-secret.png)

続いて、選んだ方法の設定に進みます。

## OAuth

1. Dify で **プラグイン** → **Outlook** を開き、**Add OAuth** の横の設定アイコンをクリックします。

   ![OAuth クライアント設定ボタン](../_assets/dify-oauth-client-button.png)

2. ダイアログに使用するリダイレクト URI が表示されるので、アプリ登録に追加します（**Authentication** → **Add Redirect URI** → **Web**）。**Client ID**、**Client Secret**、**Tenant ID**（個人アカウントやマルチテナントの場合は空欄または `common`）を入力し、Microsoft Cloud を選んで保存します。

   ![OAuth クライアント設定](../_assets/dify-oauth-client-settings.png)

3. **Add OAuth** をクリックし、ツールで使うメールボックスの Microsoft アカウントでサインインします。

> 0.7.0 より前のバージョンからアップグレードすると `Calendars.Read.Shared` が追加されます。アプリ登録に追加し、一度だけ認証し直してください。

## サービス プリンシパル

個人ではなく組織として動かすワークフローに向いています。誰もサインインする必要がなく、担当者が退職しても影響を受けず、監査ログにはアプリが記録されます。

1. 手順 1 の**アプリケーション**のアクセス許可を追加し、管理者の同意を付与します。
2. Exchange Online の [RBAC for Applications](https://learn.microsoft.com/exchange/permissions-exo/application-rbac) で、アプリが使えるメールボックスを必要なものだけに制限することをお勧めします。制限しないと、アプリケーションのアクセス許可はテナントのすべてのメールボックスに及びます。
3. Dify で **Add API Key** をクリックし、**Mode** を *Service Principal* にして、**Tenant ID**（ディレクトリ ID。`common` は不可）、**Client ID**、**Client Secret**、**Default Mailbox**（例: `support@contoso.com`）を入力します。Dify はサインインしてその受信トレイを読み取り、アクセス許可を確認します。
4. 各ツールには任意の **Mailbox** 設定があり（ノードで設定し、LLM は選べません）、同じ認証で別のメールボックスを使えます。

## ユーザーごとにサインイン: 個人用 Outlook アシスタント

チャットしている本人の「メールに何が届いてる？」「今日の予定は？」に答えるエージェントを作ります。ユーザーが初めて Outlook を必要としたとき、エージェントが Microsoft のサインイン リンクを渡します。サインイン後は、ツールがそのユーザー自身のメールボックスとカレンダーを使い、以降の会話でもサインインしたままになります。

### 1. サインイン用エンドポイントを作成する

Microsoft でのサインイン後、ブラウザーはプラグイン自身のエンドポイントに戻ってきます。

1. **プラグイン** → **Outlook** で **ENDPOINTS** までスクロールし、**+** をクリックします。

   ![エンドポイントの追加](../_assets/dify-endpoint-add.png)

2. 名前を入力して保存します。ほかに入力する項目はありません。

   ![エンドポイント名](../_assets/dify-endpoint-name.png)

3. コピー ボタンでエンドポイントの URL をコピーします。`https://<Dify のドメイン>/e/<id>/outlook/callback` の形式です。

   ![エンドポイント URL](../_assets/dify-endpoint-url.png)

> **URL が `http://localhost` で始まる場合**: セルフホストの Dify が既定値の `ENDPOINT_URL_TEMPLATE=http://localhost/e/{hook_id}` のままです。エンドポイント自体は実際のドメインで動いていて、表示される URL だけが間違っています。`docker/.env` で `ENDPOINT_URL_TEMPLATE=https://<Dify のドメイン>/e/{hook_id}` を設定して API を再起動する（`docker compose up -d api`）か、コピーした URL の `http://localhost` を Dify のアドレスに手で置き換えてください。Microsoft が `http` を受け付けるのは `localhost` だけなので、URL は `https` にする必要があります。
>
> ![localhost になっているエンドポイント URL](../_assets/dify-endpoint-url-localhost.png)

### 2. エンドポイント URL を Microsoft に登録する

アプリ登録で **Authentication** → **Add Redirect URI** → **Web** を開き、エンドポイント URL を貼り付けて **Configure** をクリックします。`localhost` ではなく `https` の URL であることを確認してください。一致しないと、Microsoft のサインイン画面で `AADSTS50011` エラーになります。

![リダイレクト URI の追加](../_assets/entra-redirect-uri.png)

### 3. Dify で認証を追加する

1. **プラグイン** → **Outlook** で **Add API Key** をクリックします。

   ![Add API Key](../_assets/dify-add-api-key.png)

2. フォームに入力します。
   - **Authorization Name**: 任意の名前（例: `Dify Outlook Agent`）。
   - **Mode**: *Each user signs in (own mailbox, for chat agents)*。
   - **Tenant ID**: ディレクトリ（テナント）ID。自組織のアカウントだけがサインインできるようになります。
   - **Client ID** と **Client Secret**: 手順 1 で取得した値。

   ![認証フォーム（上半分）](../_assets/dify-per-user-form-top.png)

   - **Default Mailbox**: 空のままにします。この方法では使いません。
   - **Sign-in Callback URL**: 1. のエンドポイント URL。`localhost` の URL は保存できません。
   - **Microsoft Cloud**: テナントが各国のクラウドにある場合を除き *Global*。

   ![認証フォーム（下半分）](../_assets/dify-per-user-form-bottom.png)

   保存時に Dify は各項目を確認し、具体的なテナント ID が入力されていれば、Microsoft がクライアント ID とシークレットを受け付けることも確認します。ユーザーのメールボックスにはアクセスせず、この認証にユーザーのトークンは保存されません。

### 4. エージェントを設定する

1. エージェントを作成し、**TOOLS** の **Add** から **Outlook** を追加します。必要なメールとカレンダーのツール、および **Sign Out of Outlook** を残します。
2. Outlook の横の認証メニューで、3. で追加した認証を選びます。OAuth の認証を選ぶと、ツールはその 1 つの共有メールボックスを使い、Sign Out of Outlook も機能しません。

   ![認証を選ぶ](../_assets/agent-credential.png)

3. 指示（プロンプト）の例:

   ```
   You can use the Outlook tools to access the current user's own mailbox and calendar.
   - When the user asks about their schedule or meetings, call list_events or search_events.
   - When the user asks about their email, call list_messages or get_message. Create a draft instead of sending unless the user clearly asks you to send.
   - If a tool says the user needs to sign in and returns a link, give the link to the user exactly as returned. Ask them to open it, sign in with their own Microsoft account, and reply "done" when finished. After they reply, call the same tool again.
   - Never make up emails or events. If a tool returns an error, tell the user what it says.
   - If the user asks to sign out or switch accounts, call outlook_sign_out.
   ```

4. エージェントを公開します。

### 5. ユーザーから見た流れ

1. 最初の質問に対して、15 分間有効なサインイン リンクが返ります。

   ![サインイン リンク](../_assets/chat-sign-in-link.png)

2. ユーザーはリンクを開き、自分の Microsoft アカウントでサインインします。

   ![アカウントの選択](../_assets/chat-choose-account.png)

3. **Signed in** というページが表示され、チャットに戻って完了したことを伝えるよう案内されます。自分で始めたサインインの場合だけ続けるようにという注意もあり、ほかの人から送られたリンクだった場合はそこで取り消せます。
4. ユーザーが「done」と返すと、エージェントがそのユーザー自身のメールボックスから回答します。サインイン後の最初の回答には使用したアカウントが示されるので、別のアカウントでサインインしてもすぐに気付けます。

   ![本人のメールボックスからの回答](../_assets/chat-answer.png)

5. 「sign out」と言うとサインインが削除され、次の質問で再びサインインを求められます。

   ![サインアウト](../_assets/chat-sign-out.png)

### サインインが続く期間

アクセス トークンはバックグラウンドで 1 時間ごとに更新され、Microsoft のリフレッシュ トークンは使われている間は有効なまま（約 90 日間使われないと失効）なので、よく使うユーザーは通常一度サインインするだけです。プラグインをアップグレードしてもサインインは維持されます。次の場合は再びサインインを求められます。

- **Dify が別のユーザーと判断した場合。** プラグインは Dify のユーザー ID でユーザーを区別します。
  - コンソール（デバッグとプレビュー）では、メンバー自身のアカウントなので変わりません。
  - **ログイン不要の公開 Web アプリ**では、ブラウザーごと（プライベート ウィンドウや Cookie の削除後も含む）に新しい匿名ユーザーとなり、それぞれサインインが必要です。
  - **Service API** では、呼び出し側が送る `user` の値です。同じ人には常に同じ値を送ってください。呼び出し側は任意の値を設定できるため、ユーザーを認証済みの信頼できるバックエンドからだけ API を呼び出してください。
  - Web アプリの URL で `sys.user_id` を渡すと ID は固定されますが、誰でも URL を書き換えて別のユーザーになりすませるため、デモ用にとどめてください。
- ユーザーがサインアウトした、パスワードを変更した、または管理者がセッションやアプリの同意を取り消した場合。
- 組織の条件付きアクセスで、一定時間ごとの再サインインが求められる場合。
- **クライアント シークレットを更新した場合**: トークンはシークレットから導出した鍵で暗号化されているため、全員がサインインし直すことになります。

### セキュリティについて

- トークンがエージェントに渡ることはありません。ツールの結果にはデータだけが含まれ、トークンは含まれないため、プロンプト インジェクションでも漏れません。各ユーザーのトークンはプラグインのストレージに暗号化して保存され、ログには出力されません。
- あるユーザーが別のユーザーのサインインを使うことはできません。ユーザー ID は LLM ではなく Dify から渡されます。
- エンドポイントが保持するのは一度しか使えない認可コードだけで、それも短時間です。トークンに交換するにはクライアント シークレットと PKCE verifier が必要ですが、エンドポイントはどちらも持ちません。
- ユーザーが自分のサインイン リンクを同僚に送ってしまう可能性があります。同僚がそのリンクでサインインすると、同僚のメールボックスが送った人のチャットにつながってしまいます。**Signed in** ページではこの点を注意し、**cancel this sign-in** で取り消せるようにしています。自分で依頼したリンクからだけサインインするよう利用者に伝えてください。管理者は Entra でユーザーのセッションを取り消すことで、どの接続でも切断できます。
- 全員の接続を一度に切るには、クライアント シークレットを更新するか、Entra でアプリの同意を取り消します。

## 各国のクラウド

OAuth、サービス プリンシパル、ユーザーごとにサインインのいずれにも **Microsoft Cloud** の設定があります（Global、US Government、US Government DoD、China（21Vianet））。サインインのホストと Microsoft Graph のホストが同時に切り替わります。既存の認証は引き続きグローバル クラウドを使います。

## 使い方

Outlook のツールをエージェントやワークフローに追加し、入力を設定して実行します。カレンダーでは **List Calendars** → **Create Event** / **List Events** がよく使う流れです。

共有されたカレンダー（例: アシスタントが役員のカレンダーを見る場合）を見るには、**List Calendar Groups** → *People's calendars* の ID を取得 → その Calendar Group ID と日付範囲で **Search Events**、または空き時間なら **Get Schedule** を使います。

## 出力変数

`text` と `json`（従来どおり）に加えて、すべてのツールが型付きの変数を返すので、後続のワークフロー ノードで `json` を解析せずに直接使えます。すべてのツールに `success`（真偽値）と `error`（文字列。成功時は空）があり、IF ノードで分岐できます。一覧系のツールはフラットな配列と `count` を返します。

| ツール | 変数（`success`、`error` 以外） |
|---|---|
| List Messages | `messages`、`count` |
| Get Message | `message_id`、`conversation_id`、`subject`、`from_name`、`from_address`、`to`、`cc`、`received_datetime`、`body`、`body_type`、`web_link`、`attachment_ids`、`attachment_names` |
| Download Attachment | `file_name`、`content_type`、`size`、`downloaded` |
| Send Message | `subject`、`to`、`attachment_count` |
| Send Draft | `draft_id`、`subject` |
| Draft Email | `draft_id`、`subject`、`conversation_id`、`web_link` |
| List Draft Emails | `drafts`、`count` |
| Add Attachment to Draft | `attachments`、`count` |
| Prioritize Email | `message_id`、`importance` |
| Flag Email | `message_id`、`flag_status` |
| List Calendar Groups | `calendar_groups`、`count` |
| List Calendars | `calendars`、`count` |
| List Events | `events`、`count`、`errors` |
| Search Events | `events`、`count`、`errors` |
| Get Schedule (Free/Busy) | `schedules`、`busy_people`、`count` |
| Create Event | `event_id`、`subject`、`start`、`end`、`time_zone`、`location`、`web_link`、`online_meeting_url` |
| Get Event | `event_id`、`subject`、`start`、`end`、`time_zone`、`location`、`web_link`、`online_meeting_url` |
| Update Event | `event_id`、`subject`、`start`、`end`、`time_zone`、`location`、`web_link`、`online_meeting_url` |
| Delete Event | `event_id` |
| Sign Out of Outlook | `signed_out` |

## トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| Microsoft の画面に `AADSTS50011: The redirect URI ... does not match` と表示される | リクエストの URL がアプリに登録されていません。**Authentication** → **Web** にまったく同じ URL を追加してください。ユーザーごとにサインインでは、`localhost` ではなく `https` のエンドポイント URL を登録します。 |
| `AADSTS7000215` / クライアント シークレットが無効 | シークレット ID ではなく **Value** を入力し、有効期限が切れていないか確認してください。 |
| `OAuth credential for tool provider ... could not be refreshed` | エージェントやノードが使っている OAuth の認証が期限切れか、取り消されています。認証し直すか、別の認証を選んでください。 |
| Sign Out of Outlook が「ワークスペースで共有された認証」と答える | エージェントが OAuth かサービス プリンシパルの認証を使っています。「ユーザーごとにサインイン」の認証を選んでください。 |
| 別のブラウザーで再びサインインを求められる | Web アプリが公開設定のため、ブラウザーごとに別の匿名 Dify ユーザーになります。[サインインが続く期間](#サインインが続く期間)を参照してください。 |
| エンドポイント URL が `http://localhost` で始まる | `ENDPOINT_URL_TEMPLATE` を設定してください。[1.](#1-サインイン用エンドポイントを作成する) を参照してください。 |
| サービス プリンシパルで特定のメールボックスに 403 が返る | アプリケーションのアクセス許可に管理者の同意がないか、Exchange の RBAC for Applications の範囲にそのメールボックスが含まれていません。 |

## プライバシー

このプラグインは、選んだ操作の入力を Microsoft Graph に送信します。「ユーザーごとにサインイン」では、各ユーザーのトークンを暗号化してプラグインのストレージに保存します。詳しくは [PRIVACY.md](../PRIVACY.md) を参照してください。
