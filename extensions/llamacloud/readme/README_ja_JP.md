## llamacloud

**作成者:** langgenius
**バージョン:** 0.0.2
**タイプ:** 拡張機能

### 説明

LlamaCloud は、UI を備えた LlamaIndex のオンライン版です。

コンテキスト検索機能を持つ AI エージェントを構築しようとしており、主に Dify のナレッジベースを使用していない場合、Dify の外部ナレッジベースを使用して、お好みの RAG ソリューションに接続できます。このプラグインは、LlamaCloud インデックスをエンドポイントとしてデプロイし、Dify 外部ナレッジベースがシームレスに接続できるようにします。

LlamaCloud でインデックスを設定するには、**Tools: Index** セクションで Create Index をクリックします。

<img src="../_assets/llamacloud_index_create.png" width="600" />

インデックスパネルでは、データのアップロード、ベクトルストレージと埋め込みモデルの接続、解析設定の構成ができます。
<img src="../_assets/llamacloud_index_panel.png" width="600" />

インデックスを設定すると、Pipeline ID が取得できます。
<img src="../_assets/llama_cloud_pipeline_id.png" width="600" />

ここで API キーを生成します：
<img src="../_assets/llama_cloud_api_key.png" width="600" />

次に、Dify のマーケットプレイスで LlamaCloud を見つけてインストールします。
ここをクリックして新しいエンドポイントを作成します：
<img src="../_assets/llamacloud_add_endpoint.png" width="600" />

エンドポイントに名前を付け、先ほど作成した API キーを貼り付けます。
<img src="../_assets/name_endpoint.png" width="600" />

新しく作成されたエンドポイント URL をコピーし、ナレッジベースに移動し、「外部ナレッジ API」、「外部ナレッジ API を追加」を選択し、「API エンドポイント」に URL を貼り付けます。

**注意：URL から "/retrieval" を削除する必要があります！！！！！** API キーについては、認証を設定していないため、任意の内容を入力できます。したがって、**エンドポイント URL を誰にも知られないようにしてください！！！**
<img src="../_assets/paste_url.png" width="600" />

外部ナレッジベースが接続されたら、「外部ナレッジベースに接続」に移動し、「ナレッジ ID」に Pipeline ID を入力し、名前を付ければ準備完了です。
<img src="../_assets/type_pipeline_id.png" width="600" />

これで、外部ナレッジベースの検索テストを実行できます。
<img src="../_assets/retrieval_testing.png" width="600" />
