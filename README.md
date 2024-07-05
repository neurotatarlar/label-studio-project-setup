## Label Studio project creator
Simple script to create projects in Label Studio. 
More precisely, it:
- creates a project in Label Studio
- creates buckets in S3 compatible storage (currently it is Yandex Cloud object storage)
- configures bucket's CORS policy
- binds bucket to the project in Label Studio

### Pre-requisites
Edit `config.yaml` file to set the desired state of the project.

Then, set credentials to `credentials.json` file in the root directory
1. Set Label Studio token. It can be found in user's setting(`/user/account`) in the Label Studio.
2. Set Yandex Cloud's static access key. You can create it after creating of a service account in the Yandex Cloud 
console. See details [here](https://yandex.cloud/en/docs/iam/operations/sa/create-access-key)
3. Set Yandex Cloud's storage OAuth token. It can be created [here](https://oauth.yandex.com/authorize?response_type=token&client_id=1a6990aa636648e9b2ef855fa7bec2fb) 

### Usage
1. Install dependencies:
```bash
pip install -r requirements.txt
```
2. Call the script:
```bash
python main.py
```