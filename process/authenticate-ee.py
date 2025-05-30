import os
import subprocess


def earth_engine_auth():
    """Check and handle Google Cloud and Earth Engine authentication."""
    # Check for existing credentials
    adc_path = os.path.expanduser('~/.config/gcloud/application_default_credentials.json')
    gcloud_authenticated = os.path.exists(adc_path)
    
    # Authenticate with Google Cloud SDK if needed
    if not gcloud_authenticated:
        try:
            subprocess.run(
                ['gcloud', 'auth', 'application-default', 'login'],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Failed to authenticate with Google Cloud SDK: {e}")
            return False
    else:
        print("Using existing Google Cloud credentials.\nIf you wish to re-authenticate with a different account, run the following command in a seperate terminal to delete the existing credentials:\ndocker exec -it ghsci bash -c 'rm -f ~/.config/gcloud/application_default_credentials.json'")

# Run the authentication command
earth_engine_auth()