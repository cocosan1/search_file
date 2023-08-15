import streamlit as st
import os
import PyPDF2
import json

import openai
from openai.embeddings_utils import cosine_similarity

from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(page_title='file serch')
st.markdown('### file serch')

OPENAI_API_KEY = st.secrets['OPENAI_API_KEY']
openai.api_key = OPENAI_API_KEY

#current working dir
cwd = os.path.dirname(__file__)

folder_name = 'search_file'


#google driveからPDFファイルの抽出
def get_files_from_gdrive():
    # Google Drive API authentication
    creds_dict = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    service = build("drive", "v3", credentials=creds)

    # Search for the folder based on its name
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
    results = service.files().list(q=query).execute()
    folders = results.get("files", [])

    if not folders:
        st.warning(f"No folder found with name: {folder_name}")
        return

    # Get the first folder's ID
    folder_id = folders[0]["id"]

    # Search for all files within the specified folder
    query = f"'{folder_id}' in parents"
    results = service.files().list(q=query).execute()
    items = results.get("files", [])

    if not items:
        st.warning(f"No files found in folder: {folder_name}")
        return

    # Download and save each file
    for item in items:
        file_id = item["id"]
        file_name = item["name"]
        # ファイルの内容をバイト列として変数に格納
        file_content = service.files().get_media(fileId=file_id).execute()

        file_path = os.path.join(cwd, 'data', file_name)
        with open(file_path, "wb") as f:
            f.write(file_content)




#PDFからテキスト抽出
def get_text_from_pdf(pdf_path):

    # PDFファイルを開く
    pdf_file = open(pdf_path, 'rb')

    # PdfReaderオブジェクトを作成
    pdf_reader = PyPDF2.PdfReader(pdf_file)

    # ページごとにテキストを抽出
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text += page.extract_text()

    # ファイルを閉じる
    pdf_file.close()

    return text


# フォルダのパスを指定
folder_path = './data/'

# フォルダ内のファイル一覧を取得
files = os.listdir(folder_path)


#enbedding後jsonファイル作成
def make_db():
    
    index = []
    for file in files:
        pdf_path = os.path.join(folder_path, file)
        doc = get_text_from_pdf(pdf_path)

        if doc:
        
            # ここでベクトル化を行う
            # openai.embeddings_utils.embeddings_utilsを使うともっとシンプルにかけます
            res = openai.Embedding.create(
                model='text-embedding-ada-002',
                input=doc
            )

            # ベクトルをデータベースに追加
            index.append({
                'title': file,
                'body': doc,
                'embedding': res['data'][0]['embedding']
            })

        else :
            index.append({
            'title': file,
            'body': doc,
            'embedding': ''
        })
        
    with open('index.json', 'w') as f:
        json.dump(index, f)

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
        #ベクトル
        query = query['data'][0]['embedding']

        # 総当りで類似度を計算
        results = map(
                lambda i: {
                    'title': i['title'],
                    'body': i['body'],
                    # ここでクエリと各文章のコサイン類似度を計算
                    'similarity': cosine_similarity(i['embedding'], query)
                    },
                INDEX
        )
        # コサイン類似度で降順（大きい順）にソート
        results = sorted(results, key=lambda i: i['similarity'], reverse=True)[:3]

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
        
        # dataフォルダ内のPDFファイル一覧を取得
        pdf_files = [f for f in os.listdir("./data") if f.endswith(".pdf")]

        if st.button("ダウンロード"):
            # 選択されたファイルをダウンロード
            with open(os.path.join("./data", slct_fname), "rb") as pdf_file:
                st.download_button(
                    label="ここをクリックしてダウンロード",
                    data=pdf_file,
                    file_name=slct_fname,
                    mime="application/pdf",
                )
    

def main():
    # アプリケーション名と対応する関数のマッピング
    apps = {
        'ファイルの検索': search_file,
        'gdriveからPDFファイルの抽出': get_files_from_gdrive,
        'PDFのindex化': make_db,

    }
    selected_app_name = st.selectbox(label='項目の選択',
                                                options=list(apps.keys()))


    # 選択されたアプリケーションを処理する関数を呼び出す
    render_func = apps[selected_app_name]
    render_func()

if __name__ == '__main__':
    main()

