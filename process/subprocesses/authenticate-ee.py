import os
import subprocess

def earth_engine_auth():
    """Check and handle Google Cloud and Earth Engine authentication."""
    adc_path = os.path.expanduser('~/.config/gcloud/application_default_credentials.json')
    
    # Check for existing credentials
    if not os.path.exists(adc_path):
        print("No existing Google Cloud credentials found.\n")
        print("If you haven't already, please register a Google Earth Engine account and setup a corresponding Google Cloud Project via the following link:")
        print("https://earthengine.google.com/noncommercial/")
        print("During the registration process, please note your unique project ID and enter it below.")
        
        # Prompt user to input their project ID
        quota_project = input("\nPlease enter your unique Google Cloud project ID: ").strip()
        
        try:
            # Interactive authentication
            print("\nInitiating Google Cloud authentication...\n")
            subprocess.run(
                ['gcloud', 'auth', 'application-default', 'login'],
                check=True,
            )
            
            # Set quota project using user input provided earlier
            if quota_project:
                print(f"\nSetting quota project to: {quota_project}")
                subprocess.run(
                    ['gcloud', 'auth', 'application-default', 'set-quota-project', quota_project],
                    check=True,
                )
                
            # Create Earth Engine assets folder
            print(f"\nCreating Earth Engine assets folder for project: {quota_project}")
            try:
                subprocess.run(
                    ['earthengine', 'create', 'folder', f'projects/{quota_project}/assets/'],
                    check=True,
                )
                print("\nSuccessfully created assets folder.")
            except subprocess.CalledProcessError as ee_error:
                print(f"\nCould not create assets folder: {ee_error}")
            
            print("\nAuthentication successful!")
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to authenticate: {e}")
            if e.stderr:
                print(e.stderr.decode())
            return False
    else:
        print("Using existing Google Cloud credentials setup previously.\n")
        print("If you wish to re-authenticate with a different account, run the following command in a seperate terminal whilst the container is running to delete the existing credentials:")
        print('docker exec -it ghsci-ee bash -c "rm -f ~/.config/gcloud/application_default_credentials.json"')

# Run the authentication command
earth_engine_auth()