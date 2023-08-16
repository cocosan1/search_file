import streamlit as st
import os
import io
import PyPDF2
import json

import openai
from openai.embeddings_utils import cosine_similarity

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

st.set_page_config(page_title='search a file')
st.markdown('### search a file')

OPENAI_API_KEY = st.secrets['OPENAI_API_KEY']
openai.api_key = OPENAI_API_KEY

# Google Drive API authentication
creds_dict = st.secrets["gcp_service_account"]
#creds_dictから読み取ったサービスアカウント情報を使用して、Googleのサービスアカウント認証情報（Credentials）を作成
creds = service_account.Credentials.from_service_account_info(creds_dict)
#Google Drive APIを使用するためのクライアントを作成
#build()関数は、指定されたAPI名（ここでは"drive"）とバージョン（ここでは"v3"）に基づいてAPIクライアントを構築
service = build("drive", "v3", credentials=creds)

#current working dir
cwd = os.path.dirname(__file__)

#tempフォルダ作成
temp_dir = "temp"
os.makedirs(temp_dir, exist_ok=True)

folder_name = 'search_file'

#db用リスト
index = []

#########################gdriveからPDFファイルのlist in dictファイルの取り出し
def get_files_from_gdrive():
   
    # Search for the folder based on its name
    #検索クエリを作成
    #folder_nameという変数に格納されているフォルダ名に基づいて、フォルダを検索
    #mimeTypeを使って検索対象をフォルダに絞り込んでいます。
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
    #files().list()メソッドを呼び出して、指定されたクエリでファイル（またはフォルダ）を検索しています。
    # qパラメータには、検索クエリが指定されています。execute()メソッドは、APIリクエストを実行し、検索結果を取得
    results = service.files().list(q=query).execute()
    #"files"キーにフォルダのリストが格納。.get()メソッドを使用して、指定されたキーから値を取得
    #もしフォルダが見つからなかった場合、空のリストがデフォルト値として返されます。
    folders = results.get("files", [])

    if not folders:
        st.warning(f"No folder found with name: {folder_name}")
        return

    # foldersリストから、最初のフォルダの情報を取得。"id"キーにアクセスしてフォルダの一意の識別子（ID）を取得
    folder_id = folders[0]["id"]

    # 'folder_id' in parentsという形式の検索クエリを組み立てています。
    # folder_idで指定されたフォルダの中にあるファイルを検索できます。
    query = f"'{folder_id}' in parents"
    #files().list()メソッドに検索クエリを指定し、.execute()メソッドを呼び出して検索結果を取得
    results = service.files().list(q=query).execute()
    #"files"キーにファイルのリストが格納されています。.get()メソッドを使用して、指定されたキーから値を取得
    #items [{},{}] キーはkind/mimeType/id/name
    items = results.get("files", [])

    return items

#############################PDFからテキスト抽出
def get_text_from_pdf(pdf_path):

    # PDFファイルを開く バイナリ読み込みモードで開き、ファイルオブジェクトpdf_fileを作成
    pdf_file = open(pdf_path, 'rb')
    # PdfReaderオブジェクトを作成しpdf_fileを読み込みます。
    # これにより、PDFファイルの内容を解析し、ページやテキストを抽出できるようになります。
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    # ページごとにテキストを抽出
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        #pdf_reader.pagesは、PDFファイル内のすべてのページにアクセスするためのリストです。
        # これを使って各ページに順番にアクセスします。
        page = pdf_reader.pages[page_num]
        #現在のページからテキストを抽出
        text += page.extract_text()

    # ファイルを閉じる
    pdf_file.close()

    return text

###########################################google driveからPDFファイルの抽出
def make_db_from_gdrive():

    #index.jsonの削除
    file_path = "./index.json"

    if os.path.exists(file_path):
        #指定したファイルパス（またはディレクトリパス）が実際に存在するかどうかを確認
        os.remove(file_path)
        st.write("index.json を削除しました。")
        st.write('テキストのindex化作業を開始します。')
    else:
        st.write("index.json は存在しません。")
        st.write('テキストのindex化作業を開始します。')

    #PDFファイル情報の抽出
    #items [{},{}] キーはkind/mimeType/id/name
    items = get_files_from_gdrive()
    st.write(items)

    if not items:
        st.warning(f"No files found in folder: {folder_name}")
        return

    # Download and save each file
    for item in items:
        file_id = item["id"]
        file_name = item["name"]
        # ファイルの内容をバイト列として変数に格納
        #get_media() メソッドは、指定したファイルID（file_id）を使用して、そのファイルのメディア（内容）を取得
        file_content = service.files().get_media(fileId=file_id).execute()

        if file_content is not None:
            file_path = os.path.join(cwd, temp_dir, file_name)
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            ######################################index化
            #PDFからテキストの抽出
            doc = get_text_from_pdf(file_path)
            st.write(doc)

            if doc:
                # openai.embeddings_utils.embeddings_utilsを使うともっとシンプルにかけます
                #テキストをベクトル化します。
                # これはOpenAIのテキスト埋め込みモデルを使用してテキストをベクトルに変換する処理
                res = openai.Embedding.create(
                    model='text-embedding-ada-002',
                    input=doc
                )

                # ベクトルをデータベースに追加
                index.append({
                    'title': file_name,
                    'body': doc,
                    'embedding': res['data'][0]['embedding'] 
                    #OpenAI Embedding APIから返されたデータ構造の中で、
                    # テキストをベクトル化した結果の埋め込みベクトルを取得するコード
                })

            else :
                pass

                
            #PDFファイルの削除
            os.remove(file_path)
            
        with open('index.json', 'w') as f:
            #json.dump() メソッドは、Pythonのデータ（通常は辞書やリストなどのオブジェクト）を
            # JSON形式のファイルに書き込むために使用
            json.dump(index, f)
        
    st.write('index.jsonの作成が完了しました。')

def search_file():
    # これが検索用の文字列
    QUERY = st.text_input('キーワードを入力してください', key='query')

    if not QUERY:
        st.stop()
    else:

        # データベースの読み込み
        with open('./index.json') as f:
            INDEX = json.load(f)

        # 検索用の文字列をベクトル化
        query = openai.Embedding.create(
            model='text-embedding-ada-002',
            input=QUERY
        )
        #ベクトル query レスポンスデータの data 内の最初の要素（インデックス [0]）には、ベクトルが含まれています。
        query = query['data'][0]['embedding']

        # 総当りで類似度を計算 新しいdictで返す
        results = map(
                #map() 関数は、イテラブル（ここでは INDEX リスト）内の各要素に対して関数を適用し、
                # その結果を新しいイテレータとして返します。
                lambda i: {
                    'title': i['title'],
                    'body': i['body'],
                    # ここでクエリと各文章のコサイン類似度を計算
                    'similarity': cosine_similarity(i['embedding'], query)
                    },
                INDEX
        )
        st.write(results)
        # コサイン類似度で降順（大きい順）にソート
        results = sorted(results, key=lambda i: i['similarity'], reverse=True)[:3]
        #lambda i: i['similarity'] を使用して 'similarity' キーの値に基づいてソート
        #reverse=True　降順　上位3件

        # 以下で結果を表示
        st.markdown("###### Rank: Title Similarity")
        fname_dict = {}
        for i, result in enumerate(results):
            st.write(f'{i+1}: {result["title"]}:  {result["similarity"]}')
            fname = result["title"]
            fname_dict[fname] = result['body']

        
        #選択したファイルのテキストを表示
        slct_fname = st.selectbox('ファイル名', fname_dict.keys(), key='slct_file')

        st.markdown('###### document')
        for dict in fname_dict:
            if dict == slct_fname:
                slct_body = fname_dict.get(dict)
                st.write(slct_body)
            else:
                continue
        
        #Gdriveから list in dictファイル
        pdf_files = get_files_from_gdrive()

        # Download and save each file
        selected_pdf = [pdf_file for pdf_file in pdf_files if pdf_file["name"] == slct_fname][0]
        file_id = selected_pdf["id"]
        
        # ファイルの内容をバイト列として変数に格納
        file_content = service.files().get_media(fileId=file_id).execute()

        file_path = os.path.join('./temp', slct_fname)
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        #PDFファイルのダウンロード
        with open(os.path.join("./temp", slct_fname), "rb") as pdf_file:
            st.download_button(
                label="download",
                data=pdf_file,
                file_name=slct_fname,
                mime="application/pdf",
            )
        
        #PDFファイルの削除
        os.remove(file_path)
        

def main():
    # アプリケーション名と対応する関数のマッピング
    apps = {
        'ファイルの検索': search_file,
        'gdriveからPDFファイル抽出 - index化 - db作成': make_db_from_gdrive,

    }
    selected_app_name = st.selectbox(label='項目の選択',
                                                options=list(apps.keys()))


    # 選択されたアプリケーションを処理する関数を呼び出す
    render_func = apps[selected_app_name]
    render_func()

if __name__ == '__main__':
    main()

