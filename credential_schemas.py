import os
import json
import requests
import yaml
from typing import List, Dict
from pathlib import Path

def print_success(message: str) -> None:
    """Print a success message in green"""
    print(f"\033[92m{message}\033[0m")

def print_error(message: str) -> None:
    """Print an error message in red"""
    print(f"\033[91m{message}\033[0m")

def print_info(message: str) -> None:
    """Print an info message in blue"""
    print(f"\033[94m{message}\033[0m")

def ensure_directory_exists(path: str) -> None:
    """Ensure that a directory exists, create it if it doesn't"""
    Path(path).mkdir(parents=True, exist_ok=True)

# Known credential types from our workflows
CREDENTIAL_TYPES = [
    "telegramApi",
    "postgres",
    "openAiApi",
    "httpHeaderAuth"
]

def load_servers() -> Dict:
    """Load server configurations from servers.yaml"""
    try:
        with open('servers.yaml', 'r') as f:
            config = yaml.safe_load(f)
            return config.get('servers', {})
    except Exception as e:
        print_error(f"Error loading servers.yaml: {str(e)}")
        return {}

def select_server(servers: Dict) -> Dict:
    """Let user select a server from the available options"""
    if not servers:
        print_error("No servers found in servers.yaml")
        exit(1)
    
    print("\nAvailable servers:")
    for idx, (server_id, server) in enumerate(servers.items(), 1):
        print(f"{idx}. {server['name']} ({server_id})")
    
    while True:
        try:
            choice = int(input("\nSelect a server (enter number): "))
            if 1 <= choice <= len(servers):
                server_id = list(servers.keys())[choice - 1]
                return servers[server_id]
            print_error("Invalid selection. Please try again.")
        except ValueError:
            print_error("Please enter a valid number.")

def get_credential_schemas(api_key: str, base_url: str) -> None:
    """Fetch and store credential schemas for known credential types"""
    headers = {"X-N8N-API-KEY": api_key}
    
    print("\nFetching credential schemas...")
    ensure_directory_exists("credential_schemas")
    
    for cred_type in CREDENTIAL_TYPES:
        try:
            response = requests.get(
                f"{base_url}/api/v1/credentials/schema/{cred_type}",
                headers=headers
            )
            
            if response.status_code == 200:
                schema = response.json()
                
                # Save schema to file
                schema_file = os.path.join("credential_schemas", f"{cred_type}.json")
                with open(schema_file, 'w', encoding='utf-8') as f:
                    json.dump(schema, f, indent=2)
                print_success(f"  ✓ Saved schema for {cred_type}")
            else:
                print_error(f"  ✗ Failed to get schema for {cred_type}: {response.status_code}")
                
        except Exception as e:
            print_error(f"  ✗ Error fetching schema for {cred_type}: {str(e)}")

def get_schema(cred_type: str) -> Dict:
    """Get a credential schema from file"""
    schema_file = os.path.join("credential_schemas", f"{cred_type}.json")
    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print_error(f"Error loading schema for {cred_type}: {str(e)}")
        return {}

def list_available_schemas() -> List[str]:
    """List all available credential schemas"""
    schema_dir = "credential_schemas"
    if not os.path.exists(schema_dir):
        return []
    
    return [f.replace('.json', '') for f in os.listdir(schema_dir) 
            if f.endswith('.json')]

def generate_credential_example(schema: Dict, cred_type: str) -> Dict:
    """Generate an example credential configuration based on the schema"""
    # Create a credential ID based on the type
    cred_id = cred_type.lower()
    
    example = {
        "environments": {
            "production": {
                "name": "Production Environment",
                "postfix": "Prod",
                "credentials": {
                    cred_id: {
                        "type": cred_type,
                        "name": f"Example {cred_type} Credential",
                        "data": {}
                    }
                }
            },
            "development": {
                "name": "Development Environment",
                "postfix": "Dev",
                "credentials": {
                    cred_id: {
                        "type": cred_type,
                        "name": f"Example {cred_type} Credential",
                        "data": {}
                    }
                }
            }
        }
    }
    
    # Extract all fields from schema properties
    if "properties" in schema:
        for field, props in schema["properties"].items():
            # Get field type and description
            field_type = props.get("type", "string")
            description = props.get("description", "")
            
            # Generate example value based on field type
            if field_type == "string":
                example_value = "example_string_value"
            elif field_type == "number":
                example_value = 0
            elif field_type == "boolean":
                example_value = False
            elif field_type == "array":
                example_value = []
            elif field_type == "object":
                example_value = {}
            else:
                example_value = "example_value"
            
            # Add field to both environments
            example["environments"]["production"]["credentials"][cred_id]["data"][field] = example_value
            example["environments"]["development"]["credentials"][cred_id]["data"][field] = example_value
            
            # Add description as comment if available
            if description:
                example["environments"]["production"]["credentials"][cred_id]["data"][f"# {field}"] = description
                example["environments"]["development"]["credentials"][cred_id]["data"][f"# {field}"] = description
    
    return example

def show_credential_examples() -> None:
    """Show example credential configurations for available schemas"""
    schemas = list_available_schemas()
    if not schemas:
        print_error("No credential schemas found. Please download schemas first.")
        return
    
    print("\nAvailable credential types:")
    for idx, schema in enumerate(schemas, 1):
        print(f"{idx}. {schema}")
    
    while True:
        try:
            choice = int(input("\nSelect a credential type to view example (enter number): "))
            if 1 <= choice <= len(schemas):
                cred_type = schemas[choice - 1]
                schema = get_schema(cred_type)
                if schema:
                    example = generate_credential_example(schema, cred_type)
                    print_info(f"\nExample credential configuration for {cred_type}:")
                    print("\nCopy this into your credentials.yaml:")
                    print("---")
                    print(yaml.dump(example, default_flow_style=False, sort_keys=False))
                    return
            print_error("Invalid selection. Please try again.")
        except ValueError:
            print_error("Please enter a valid number.")

def main_menu() -> None:
    """Display and handle the main menu"""
    while True:
        print("\nCredential Schema Management")
        print("1. Download credential schemas from server")
        print("2. View example credential configurations")
        print("3. Exit")
        
        try:
            choice = int(input("\nSelect an option (enter number): "))
            if choice == 1:
                servers = load_servers()
                selected_server = select_server(servers)
                api_key = selected_server['api_key']
                base_url = selected_server['url']
                print(f"\nUsing server: {selected_server['name']}")
                get_credential_schemas(api_key, base_url)
            elif choice == 2:
                show_credential_examples()
            elif choice == 3:
                print_info("Goodbye!")
                break
            else:
                print_error("Invalid selection. Please try again.")
        except ValueError:
            print_error("Please enter a valid number.")

if __name__ == "__main__":
    main_menu()
