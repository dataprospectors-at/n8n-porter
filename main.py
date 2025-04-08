from typing import List, Dict, Optional, Tuple
import requests
import os
from dotenv import load_dotenv
import yaml
import json
from pathlib import Path
from datetime import datetime
import sys

def print_summary(message: str) -> None:
    """Print a summary header in blue color.

    Args:
        message (str): The message to display as a summary header.
    """
    print(f"\n\033[94m=== {message} ===\033[0m")

def print_success(message: str) -> None:
    """Print a success message in green color.

    Args:
        message (str): The success message to display.
    """
    print(f"\033[92m✓ {message}\033[0m")

def print_error(message: str) -> None:
    """Print an error message in red color.

    Args:
        message (str): The error message to display.
    """
    print(f"\033[91m✗ {message}\033[0m")

def get_all_projects(api_key: str, base_url: str) -> List[Dict]:
    """Get all available projects from n8n instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.

    Returns:
        List[Dict]: List of project dictionaries containing project information.
    """
    headers = {"X-N8N-API-KEY": api_key}
    try:
        response = requests.get(f"{base_url}/api/v1/projects", headers=headers)
        if response.status_code == 200:
            return response.json().get('data', [])
        elif response.status_code == 403:
            print_error("Project listing not allowed, probably on local instance.")
            return []
        else:
            print_error(f"Failed to get projects: {response.status_code}")
            return []
    except Exception as e:
        print_error(f"Error getting projects: {str(e)}")
        return []

def create_project(api_key: str, base_url: str, name: str) -> Optional[str]:
    """Create a new project in n8n instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        name (str): Name of the project to create.

    Returns:
        Optional[str]: The ID of the created project if successful, None otherwise.
    """
    headers = {
        "X-N8N-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(
            f"{base_url}/api/v1/projects",
            headers=headers,
            json={"name": name}
        )
        
        if response.status_code in [200, 201]:
            project_id = response.json().get('id')
            print_success(f"Created project: {name}")
            return project_id
        else:
            print_error(f"Failed to create project: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Error creating project: {str(e)}")
        return None

def create_credential(api_key: str, base_url: str, credential_data: Dict, credential_type: str, env_postfix: str = "") -> Optional[str]:
    """Create a new credential in n8n instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        credential_data (Dict): Dictionary containing credential information.
        credential_type (str): Type of the credential to create.
        env_postfix (str): Environment postfix to append to credential name.

    Returns:
        Optional[str]: The ID of the created credential if successful, None otherwise.
    """
    url = f"{base_url}/api/v1/credentials"
    headers = {
        "X-N8N-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    # Get all possible postfixes from environments
    try:
        with open('credentials.yaml', 'r') as f:
            creds_config = yaml.safe_load(f)
            all_postfixes = [
                env.get('postfix', '').strip()
                for env in creds_config.get('environments', {}).values()
                if env.get('postfix', '').strip()
            ]
    except Exception as e:
        print_error(f"Warning: Could not load postfixes from credentials.yaml: {str(e)}")
        all_postfixes = []

    # Clean the credential name and remove any existing postfix
    name = credential_data["name"].strip()
    for postfix in all_postfixes:
        if name.endswith(f" {postfix}"):
            name = name[:-len(f" {postfix}")].strip()
            break

    # Add new postfix if provided
    if env_postfix:
        name = f"{name} {env_postfix}"

    payload = {
        "name": name,
        "type": credential_type,
        "data": credential_data["data"]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            credential = response.json()
            save_resource_mapping(base_url, 'credentials', credential['id'], credential['name'])
            print_success(f"Created credential: {credential['name']}")
            return credential['id']
        else:
            print_error(f"Failed to create credential {name}: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Error creating credential {name}: {str(e)}")
        return None

def get_workflows(api_key: str, base_url: str, project_id: Optional[str]) -> List[Dict]:
    """Get all workflows from a project or instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        project_id (Optional[str]): ID of the project to get workflows from. If None, gets all workflows.

    Returns:
        List[Dict]: List of workflow dictionaries containing workflow information.
    """
    headers = {"X-N8N-API-KEY": api_key}
    try:
        params = {"projectId": project_id} if project_id else {}
        response = requests.get(
            f"{base_url}/api/v1/workflows",
            headers=headers,
            params=params
        )
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            print_error(f"Failed to get workflows: {response.status_code}")
            return []
    except Exception as e:
        print_error(f"Error getting workflows: {str(e)}")
        return []

def get_environment_replacements(creds_config: Dict, env_type: str) -> Dict[str, str]:
    """Get string replacements for the target environment.

    Args:
        creds_config (Dict): Configuration dictionary containing replacement mappings.
        env_type (str): Type of environment (e.g., 'production', 'development', 'staging').

    Returns:
        Dict[str, str]: Dictionary mapping old values to new values based on environment.
    """
    replacements = {}
    replacements_config = creds_config.get('replacements', {})
    
    for replacement_name, replacement_data in replacements_config.items():
        values = replacement_data.get('values', {})
        if env_type in values:
            # For each environment value, we need to replace all other environment values
            target_value = values[env_type]
            for other_env, other_value in values.items():
                if other_env != env_type:
                    replacements[other_value] = target_value
            
    return replacements

def create_workflow(api_key: str, base_url: str, workflow_data: Dict, project_id: str, 
                   credential_mapping: Dict, sf_id_mapping: Dict = None, env_type: str = 'dev', 
                   supports_projects: bool = True, env_postfix: str = "") -> Optional[str]:
    """Create a new workflow in n8n instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        workflow_data (Dict): Dictionary containing workflow information.
        project_id (str): ID of the project to create the workflow in.
        credential_mapping (Dict): Dictionary mapping credential names to IDs.
        sf_id_mapping (Dict, optional): Dictionary mapping subflow IDs. Defaults to None.
        env_type (str, optional): Type of environment. Defaults to 'dev'.
        supports_projects (bool, optional): Whether the instance supports projects. Defaults to True.
        env_postfix (str): Environment postfix to append to credential names.

    Returns:
        Optional[str]: The ID of the created workflow if successful, None otherwise.
    """
    headers = {
        "X-N8N-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    
    workflow_payload = json.loads(json.dumps(workflow_data))
    
    try:
        with open('credentials.yaml', 'r') as f:
            creds_config = yaml.safe_load(f)
        replacements = get_environment_replacements(creds_config, env_type)
        
        workflow_str = json.dumps(workflow_payload)
        
        for old_value, new_value in replacements.items():
            workflow_str = workflow_str.replace(old_value, new_value)
        
        workflow_payload = json.loads(workflow_str)
        
    except Exception as e:
        print_error(f"Warning: Could not apply string replacements: {str(e)}")
        workflow_payload = workflow_data

    workflow_payload.update({
        "settings": {
            "saveExecutionProgress": workflow_payload.get('settings', {}).get('saveExecutionProgress', True),
            "saveManualExecutions": workflow_payload.get('settings', {}).get('saveManualExecutions', True),
            "saveDataErrorExecution": workflow_payload.get('settings', {}).get('saveDataErrorExecution', 'all'),
            "executionTimeout": workflow_payload.get('settings', {}).get('executionTimeout', 3600),
            "errorWorkflow": workflow_payload.get('settings', {}).get('errorWorkflow', '')
        }
    })
    
    if 'nodes' in workflow_payload:
        for node in workflow_payload['nodes']:
            if 'credentials' in node:
                for cred_type, cred_data in node['credentials'].items():
                    old_name = cred_data.get('name', '')
                    # Remove any existing postfix and whitespace
                    base_name = old_name.split(' ')[0] if ' ' in old_name else old_name
                    
                    matching_cred = None
                    for cred_key, new_id in credential_mapping.items():
                        cred_base_name = cred_key.split(' ')[0] if ' ' in cred_key else cred_key
                        if (cred_base_name.lower() == base_name.lower() or 
                            cred_base_name.replace('_', ' ').lower() == base_name.lower()):
                            matching_cred = new_id
                            break
                    
                    if matching_cred:
                        cred_data['id'] = matching_cred
                    else:
                        print_error(f"No matching credential found for: {old_name}")
            
            if node.get('type') == 'n8n-nodes-base.executeWorkflow' and sf_id_mapping:
                params = node.get('parameters', {})
                old_workflow_id = params.get('workflowId')
                
                if isinstance(old_workflow_id, str) and old_workflow_id in sf_id_mapping:
                    params['workflowId'] = sf_id_mapping[old_workflow_id]
                    print_success(f"Updated subworkflow reference in node '{node.get('name')}': {old_workflow_id} → {sf_id_mapping[old_workflow_id]}")
                elif isinstance(old_workflow_id, dict):
                    old_id = old_workflow_id.get('value')
                    if old_id and old_id in sf_id_mapping:
                        old_workflow_id['value'] = sf_id_mapping[old_id]
                        print_success(f"Updated subworkflow reference in node '{node.get('name')}': {old_id} → {sf_id_mapping[old_id]}")
                        if 'cachedResultName' in old_workflow_id:
                            old_workflow_id['cachedResultName'] = old_workflow_id['cachedResultName'].split(' ')[0]
            
            elif node.get('type') == '@n8n/n8n-nodes-langchain.toolWorkflow' and sf_id_mapping:
                params = node.get('parameters', {})
                old_workflow_id = params.get('workflowId')
                
                if isinstance(old_workflow_id, dict):
                    old_id = old_workflow_id.get('value')
                    if old_id and old_id in sf_id_mapping:
                        old_workflow_id['value'] = sf_id_mapping[old_id]
                        print_success(f"Updated subworkflow reference in tool node '{node.get('name')}': {old_id} → {sf_id_mapping[old_id]}")
                        if 'cachedResultName' in old_workflow_id:
                            old_workflow_id['cachedResultName'] = old_workflow_id['cachedResultName'].split(' ')[0]
    
    create_payload = {
        "name": workflow_payload['name'],
        "nodes": workflow_payload['nodes'],
        "connections": workflow_payload['connections'],
        "settings": workflow_payload.get('settings', {})
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/workflows",
            headers=headers,
            json=create_payload
        )
        
        if response.status_code != 200:
            error_detail = response.json() if response.text else "No error details available"
            print_error(f"Failed to create workflow {workflow_payload['name']}: Status {response.status_code}")
            print_error(f"Error details: {error_detail}")
            return None
            
        workflow_id = response.json().get('id')
        
        if supports_projects:
            transfer_response = requests.put(
                f"{base_url}/api/v1/workflows/{workflow_id}/transfer",
                headers=headers,
                json={"destinationProjectId": project_id}
            )
            
            if transfer_response.status_code not in [200, 204]:
                error_detail = transfer_response.json() if transfer_response.text else "No error details available"
                print_error(f"Failed to transfer workflow {workflow_payload['name']}: Status {transfer_response.status_code}")
                print_error(f"Error details: {error_detail}")
                try:
                    requests.delete(f"{base_url}/api/v1/workflows/{workflow_id}", headers=headers)
                    print_error("Cleaned up partially created workflow")
                except Exception as cleanup_error:
                    print_error(f"Error during cleanup: {str(cleanup_error)}")
                return None
        
        save_resource_mapping(base_url, 'workflows', workflow_id, workflow_payload['name'])
        print_success(f"Created workflow: {workflow_payload['name']}")
        return workflow_id
        
    except Exception as e:
        print_error(f"Error creating workflow {workflow_payload['name']}")
        print_error(f"Error details: {str(e)}")
        return None

def save_mapping_info(filename: str, mapping_data: Dict) -> None:
    """Save mapping information to a JSON file.

    Args:
        filename (str): Name of the file to save mappings to.
        mapping_data (Dict): Dictionary containing mapping information.
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(mapping_data, f, indent=2)
        print_success(f"Saved mapping information to {filename}")
    except Exception as e:
        print_error(f"Failed to save mapping information: {str(e)}")

def ensure_directory_exists(path: str) -> None:
    """Ensure that a directory exists, create it if it doesn't.

    Args:
        path (str): Path of the directory to ensure exists.
    """
    Path(path).mkdir(parents=True, exist_ok=True)

def save_workflow(workflow: Dict, base_path: str, subfolder: str) -> None:
    """Save a workflow to the specified path and subfolder.

    Args:
        workflow (Dict): Dictionary containing workflow information.
        base_path (str): Base path to save the workflow.
        subfolder (str): Subfolder within the base path to save the workflow.
    """
    filepath = Path(base_path) / subfolder / f"{workflow['name']}_{workflow['id']}.json"
    try:
        ensure_directory_exists(filepath.parent)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print_error(f"Failed to save workflow {workflow['name']}: {str(e)}")

def select_project(projects: List[Dict]) -> Optional[Dict]:
    """Let user select a project from the list.

    Args:
        projects (List[Dict]): List of project dictionaries to choose from.

    Returns:
        Optional[Dict]: Selected project dictionary if successful, None otherwise.
    """
    while True:
        try:
            choice = int(input("\nSelect a project (number): ")) - 1
            if 0 <= choice < len(projects):
                return projects[choice]
            print_error("Invalid choice. Please try again.")
        except ValueError:
            print_error("Please enter a number.")
    return None

def perform_backup(api_key: str, base_url: str, project: Dict, supports_projects: bool, server_name: str) -> None:
    """Backup all workflows from an n8n instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        project (Dict): Dictionary containing project information.
        supports_projects (bool): Whether the instance supports projects.
        server_name (str): Name of the server from servers.yaml.
    """
    print("\nFetching workflows...")
    workflows = get_workflows(api_key, base_url, project.get('id'))
    
    if not workflows:
        print_error("No workflows found to backup")
        return
    print_success(f"Found {len(workflows)} workflows")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Sanitize server name for use in filename
    sanitized_server_name = "".join(c for c in server_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
    backup_path = Path("data") / f"backup_{sanitized_server_name}_{project['name']}_{timestamp}"
    print(f"\nCreating backup directory: {backup_path}")
    ensure_directory_exists(backup_path)
    
    print("\nSaving workflows...")
    for i, workflow in enumerate(workflows, 1):
        save_workflow(workflow, backup_path, "workflows")
        print(f"Progress: {i}/{len(workflows)} workflows saved", end='\r')
    
    print("\n")
    print_success(f"Backup complete! {len(workflows)} workflows saved to {backup_path}")

def analyze_workflow_dependencies(workflow: Dict) -> List[str]:
    """Analyze a workflow to find all its dependencies (referenced workflows).

    Args:
        workflow (Dict): Dictionary containing workflow information.

    Returns:
        List[str]: List of workflow IDs that this workflow depends on.
    """
    dependencies = []
    
    if 'nodes' not in workflow:
        return dependencies
        
    for node in workflow['nodes']:
        # Check for executeWorkflow nodes
        if node.get('type') == 'n8n-nodes-base.executeWorkflow':
            params = node.get('parameters', {})
            workflow_id = params.get('workflowId')
            if isinstance(workflow_id, str):
                dependencies.append(workflow_id)
            elif isinstance(workflow_id, dict):
                old_id = workflow_id.get('value')
                if old_id:
                    dependencies.append(old_id)
                    
        # Check for toolWorkflow nodes
        elif node.get('type') == '@n8n/n8n-nodes-langchain.toolWorkflow':
            params = node.get('parameters', {})
            workflow_id = params.get('workflowId')
            if isinstance(workflow_id, dict):
                old_id = workflow_id.get('value')
                if old_id:
                    dependencies.append(old_id)
    
    return dependencies

def build_dependency_graph(workflows: List[Dict]) -> Dict[str, List[str]]:
    """Build a graph of workflow dependencies.

    Args:
        workflows (List[Dict]): List of all workflows.

    Returns:
        Dict[str, List[str]]: Dictionary mapping workflow IDs to their dependencies.
    """
    graph = {}
    for workflow in workflows:
        workflow_id = workflow['id']
        graph[workflow_id] = analyze_workflow_dependencies(workflow)
    return graph

def get_workflow_order(graph: Dict[str, List[str]]) -> List[str]:
    """Determine the order in which workflows should be created based on dependencies.

    Args:
        graph (Dict[str, List[str]]): Dictionary mapping workflow IDs to their dependencies.

    Returns:
        List[str]: List of workflow IDs in the order they should be created.
    """
    # Create a copy of the graph to modify
    remaining = graph.copy()
    order = []
    
    while remaining:
        # Find workflows with no remaining dependencies
        ready = [workflow_id for workflow_id, deps in remaining.items() 
                if not any(dep in remaining for dep in deps)]
        
        if not ready:
            # If no ready workflows but still have remaining, we have a cycle
            raise ValueError("Circular dependency detected in workflows")
            
        # Add ready workflows to order and remove them from remaining
        order.extend(ready)
        for workflow_id in ready:
            del remaining[workflow_id]
    
    return order

def perform_restore(api_key: str, base_url: str, project: Dict, supports_projects: bool, target_env: str) -> None:
    """Restore workflows to an n8n instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        project (Dict): Dictionary containing project information.
        supports_projects (bool): Whether the instance supports projects.
        target_env (str): Target environment to restore to ('production' or 'development').
    """
    stats = {
        'workflows_created': 0,
        'workflows_failed': 0,
        'credentials_created': 0,
        'credentials_failed': 0
    }

    print("\nLoading credentials configuration...")
    try:
        with open('credentials.yaml', 'r') as f:
            creds_config = yaml.safe_load(f)
        print_success("Credentials configuration loaded")
    except Exception as e:
        print_error(f"Error loading credentials.yaml: {str(e)}")
        return

    print_summary("Restore Process")
    print(f"Target Server: {base_url}")
    print(f"Project: {project['name']}")
    print(f"Target environment: {target_env}")
    print(f"Project support: {'Yes' if supports_projects else 'No'}")
    
    data_dir = Path("data")
    if not data_dir.exists():
        print_error("No backups found. Data directory doesn't exist.")
        return
        
    backups = [d for d in data_dir.iterdir() if d.is_dir() and d.name.startswith("backup_")]
    if not backups:
        print_error("No backups found in data directory.")
        return

    print("\nAvailable backups:")
    for i, backup in enumerate(backups, 1):
        print(f"{i}. {backup.name}")

    while True:
        try:
            choice = int(input("\nSelect backup to restore (number): ")) - 1
            if 0 <= choice < len(backups):
                backup_dir = backups[choice]
                break
            print_error("Invalid choice. Please try again.")
        except ValueError:
            print_error("Please enter a number.")

    workflow_dir = backup_dir / "workflows"
    if not workflow_dir.exists():
        print_error(f"No workflows found in backup {backup_dir.name}")
        return

    print("\nLoading workflows from backup...")
    workflows = []
    for workflow_file in workflow_dir.glob("*.json"):
        try:
            with open(workflow_file, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
                workflows.append(workflow)
        except Exception as e:
            print_error(f"Error loading workflow {workflow_file.name}: {str(e)}")

    if not workflows:
        print_error("No workflows found in backup")
        return

    print_success(f"Found {len(workflows)} workflows to restore")

    print("\nCreating credentials...")
    credential_mapping = {}
    
    if creds_config and 'environments' in creds_config and target_env in creds_config['environments']:
        env_data = creds_config['environments'][target_env]
        env_credentials = env_data.get('credentials', {})
        env_name = env_data.get('name', target_env.title())
        env_postfix = env_data.get('postfix', '').strip()
        
        print_success(f"Using environment: {env_name}")
        if env_postfix:
            print_success(f"Environment postfix: {env_postfix}")
        
        for cred_key, cred_data in env_credentials.items():
            try:
                credential_data = {
                    "name": cred_data['name'],
                    "data": cred_data['data']
                }
                
                new_cred_id = create_credential(api_key, base_url, credential_data, cred_data['type'], env_postfix)
                
                if new_cred_id:
                    credential_mapping[cred_key] = new_cred_id
                    credential_mapping[cred_data['name']] = new_cred_id
                    stats['credentials_created'] += 1
                    print_success(f"Created credential: {cred_data['name']}{' ' + env_postfix if env_postfix else ''}")
                else:
                    stats['credentials_failed'] += 1
                    print_error(f"Failed to create credential: {cred_data['name']}{' ' + env_postfix if env_postfix else ''}")
                    
            except Exception as e:
                stats['credentials_failed'] += 1
                print_error(f"Error processing credential {cred_data['name']}: {str(e)}")
    else:
        print_error(f"No credentials found for environment: {target_env}")
        return

    print("\nAnalyzing workflow dependencies...")
    try:
        dependency_graph = build_dependency_graph(workflows)
        workflow_order = get_workflow_order(dependency_graph)
        print_success(f"Found {len(workflow_order)} workflows to create in correct order")
    except ValueError as e:
        print_error(f"Error analyzing dependencies: {str(e)}")
        return

    print("\nCreating workflows in dependency order...")
    workflow_mapping = {}
    for workflow_id in workflow_order:
        # Find the workflow data
        workflow_data = next(w for w in workflows if w['id'] == workflow_id)
        
        # Create the workflow
        new_id = create_workflow(api_key, base_url, workflow_data, project.get('id'), 
                               credential_mapping, workflow_mapping, target_env, supports_projects,
                               env_postfix)
        
        if new_id:
            stats['workflows_created'] += 1
            workflow_mapping[workflow_id] = new_id
            print_success(f"Created workflow: {workflow_data['name']}")
        else:
            stats['workflows_failed'] += 1
            print_error(f"Failed to create workflow: {workflow_data['name']}")

    print_summary("Restore Complete")
    print(f"Credentials: {stats['credentials_created']} created, {stats['credentials_failed']} failed")
    print(f"Workflows: {stats['workflows_created']} created, {stats['workflows_failed']} failed")

def load_server_config() -> Dict:
    """Load server configuration from servers.yaml file.

    Returns:
        Dict: Dictionary containing server configuration.

    Raises:
        SystemExit: If servers.yaml is not found or cannot be loaded.
    """
    try:
        with open('servers.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print_error("servers.yaml not found. Please copy servers.yaml.example to servers.yaml and configure your servers.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Error loading servers.yaml: {str(e)}")
        sys.exit(1)

def print_menu(title: str, options: List[str]) -> int:
    """Display a menu and return user's choice.

    Args:
        title (str): Title of the menu.
        options (List[str]): List of menu options.

    Returns:
        int: Index of the selected option.
    """
    print_summary(title)
    for i, option in enumerate(options, 1):
        print(f"{i}. {option}")
    
    while True:
        try:
            choice = int(input("\nSelect option (number): ")) - 1
            if 0 <= choice < len(options):
                return choice
            print_error("Invalid choice. Please try again.")
        except ValueError:
            print_error("Please enter a number.")

def select_server(servers: Dict) -> Tuple[str, Dict]:
    """Let user select a server from the list.

    Args:
        servers (Dict): Dictionary containing server configurations.

    Returns:
        Tuple[str, Dict]: Tuple containing selected server name and configuration.
    """
    server_names = list(servers['servers'].keys())
    server_options = [f"{servers['servers'][name]['name']} ({name})" 
                     for name in server_names]
    
    choice = print_menu("Select Server", server_options)
    selected_name = server_names[choice]
    return selected_name, servers['servers'][selected_name]

def get_or_create_project(api_key: str, base_url: str, server_config: Dict) -> Optional[Dict]:
    """Get existing project or handle non-project server.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        server_config (Dict): Dictionary containing server configuration.

    Returns:
        Optional[Dict]: Dictionary containing project information if successful, None otherwise.
    """
    if not server_config.get('supports_projects', False):
        return {
            'id': None,
            'name': 'default'
        }
    
    projects = get_all_projects(api_key, base_url)
    if not projects:
        print_error("No projects found")
        return None
    
    project_options = [f"{project['name']} (ID: {project['id']})" 
                      for project in projects]
    
    choice = print_menu("Select Project", project_options)
    return projects[choice]

def validate_configs() -> bool:
    """Validate configuration files exist and have correct structure.

    Returns:
        bool: True if all required configuration files exist, False otherwise.
    """
    required_files = ['servers.yaml', 'credentials.yaml']
    for file in required_files:
        if not Path(file).exists():
            print_error(f"Missing {file}. Please copy {file}.example and configure it.")
            return False
    return True

def test_api_connection(api_key: str, base_url: str) -> bool:
    """Test if the API key is valid and the connection works.

    Args:
        api_key (str): The API key to test.
        base_url (str): The base URL of the n8n instance.

    Returns:
        bool: True if the connection is successful, False otherwise.
    """
    headers = {"X-N8N-API-KEY": api_key}
    try:
        # Try to get workflows, which is a core API endpoint
        response = requests.get(f"{base_url}/api/v1/workflows", headers=headers)
        if response.status_code == 200:
            print_success("API connection successful")
            return True
        else:
            print_error(f"API connection failed: {response.status_code}")
            print_error(f"Error details: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Failed to connect to n8n instance. Is it running?")
        return False
    except Exception as e:
        print_error(f"Error testing API connection: {str(e)}")
        return False

def main() -> None:
    """Main entry point for the n8n workflow migration tool."""
    while True:
        print_summary("N8N Workflow Migration Tool")
        
        if not validate_configs():
            return

        try:
            with open('servers.yaml', 'r') as f:
                servers = yaml.safe_load(f)
        except Exception as e:
            print_error(f"Error loading servers.yaml: {str(e)}")
            return

        print("\nWhat would you like to do?")
        print("1. Backup workflows")
        print("2. Restore workflows")
        print("3. Delete all workflows and credentials")
        print("4. Exit")
        choice = input("Enter your choice (1-4): ")

        if choice == '4':
            print_success("Goodbye!")
            return

        if choice not in ['1', '2', '3']:
            print_error("Invalid choice. Please select 1, 2, 3, or 4")
            continue

        server_name, server_config = select_server(servers)
        api_key = server_config['api_key']
        base_url = server_config['url']
        supports_projects = server_config.get('supports_projects', False)
        
        print_success(f"Selected server: {server_config['name']}")
        print_success(f"Projects supported: {'Yes' if supports_projects else 'No'}")
        
        # Test API connection before proceeding
        if not test_api_connection(api_key, base_url):
            print_error("Failed to connect to n8n instance. Please check your API key and make sure the instance is running.")
            continue
        
        if supports_projects:
            print_summary("Project Selection")
            project = get_or_create_project(api_key, base_url, server_config)
        else:
            print_summary("Using Default Project")
            project = {'id': None, 'name': 'default'}
            print_success("Using default project (no project support)")
        
        if project is None:
            continue
            
        if choice == '1':
            print_summary(f"Starting Backup from {server_config['name']}")
            print(f"Project: {project['name']}")
            perform_backup(api_key, base_url, project, supports_projects, server_name)
        elif choice == '2':
            print_summary(f"Starting Restore to {server_config['name']}")
            print(f"Target Project: {project['name']}")
            
            env_choice = print_menu("Select Target Environment", [
                "Production",
                "Development"
            ])
            target_env = ["production", "development"][env_choice]
            
            print_success(f"Using {target_env} credentials")
            perform_restore(api_key, base_url, project, supports_projects, target_env)
        elif choice == '3':
            perform_cleanup(api_key, base_url, project)

        # Wait for user to press any key before continuing
        input("\nPress Enter to continue...")

def perform_cleanup(api_key: str, base_url: str, project: Dict) -> None:
    """Delete all workflows and credentials from an instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        project (Dict): Dictionary containing project information.
    """
    print("\nWarning: This will delete ONLY the workflows and credentials that were automatically created")
    print("and are tracked in resource_mapping.json. Any manually created resources will not be affected.")
    confirm = input("Are you sure you want to proceed? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("Operation cancelled.")
        return

    stats = {
        'workflows_deleted': 0,
        'workflows_failed': 0,
        'credentials_deleted': 0,
        'credentials_failed': 0
    }

    resources = get_instance_resources(base_url)

    if not resources['workflows'] and not resources['credentials']:
        print("\nNo tracked resources found in resource_mapping.json for this instance.")
        print("This means either:")
        print("1. No resources were created using this tool yet")
        print("2. All tracked resources have already been deleted")
        print("3. Resources were created manually and are not tracked")
        return

    print("\nDeleting credentials...")
    for cred_id, cred_name in resources['credentials'].items():
        try:
            delete_credential(api_key, base_url, cred_id)
            stats['credentials_deleted'] += 1
            print_success(f"Deleted credential: {cred_name}")
        except Exception as e:
            stats['credentials_failed'] += 1
            print_error(f"Failed to delete credential {cred_name}: {str(e)}")

    print("\nDeleting workflows...")
    for workflow_id, workflow_name in resources['workflows'].items():
        try:
            delete_workflow(api_key, base_url, workflow_id)
            stats['workflows_deleted'] += 1
            print_success(f"Deleted workflow: {workflow_name}")
        except Exception as e:
            stats['workflows_failed'] += 1
            print_error(f"Failed to delete workflow {workflow_name}: {str(e)}")

    if project.get('id') and project['id'] in resources['projects']:
        try:
            delete_project(api_key, base_url, project['id'])
            print_success(f"Deleted project: {project['name']}")
        except Exception as e:
            print_error(f"Failed to delete project {project['name']}: {str(e)}")

    print("\nCleanup Summary:")
    print(f"Credentials deleted: {stats['credentials_deleted']}")
    print(f"Credentials failed to delete: {stats['credentials_failed']}")
    print(f"Workflows deleted: {stats['workflows_deleted']}")
    print(f"Workflows failed to delete: {stats['workflows_failed']}")
    print("\nNote: Only resources tracked in resource_mapping.json were affected.")

def get_workflow_by_id(api_key: str, base_url: str, workflow_id: str) -> Optional[Dict]:
    """Get a specific workflow by its ID.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        workflow_id (str): ID of the workflow to retrieve.

    Returns:
        Optional[Dict]: Dictionary containing workflow information if successful, None otherwise.
    """
    headers = {"X-N8N-API-KEY": api_key}
    try:
        response = requests.get(
            f"{base_url}/api/v1/workflows/{workflow_id}",
            headers=headers
        )
        if response.status_code == 200:
            return response.json()
        else:
            print_error(f"Failed to get workflow {workflow_id}: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Error getting workflow {workflow_id}: {str(e)}")
        return None

def remove_resource_mapping(instance_url: str, resource_type: str, resource_id: str) -> None:
    """Remove resource mapping from local storage.

    Args:
        instance_url (str): URL of the n8n instance.
        resource_type (str): Type of resource (workflows, credentials, projects).
        resource_id (str): ID of the resource to remove.
    """
    storage_file = 'resource_mapping.json'
    try:
        if os.path.exists(storage_file):
            with open(storage_file, 'r') as f:
                mappings = json.load(f)
            
            if (instance_url in mappings and 
                resource_type in mappings[instance_url] and 
                resource_id in mappings[instance_url][resource_type]):
                del mappings[instance_url][resource_type][resource_id]
                
                with open(storage_file, 'w') as f:
                    json.dump(mappings, f, indent=2)

    except Exception as e:
        print_error(f"Failed to remove resource mapping: {str(e)}")

def delete_workflow(api_key: str, base_url: str, workflow_id: str) -> None:
    """Delete a workflow by ID.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        workflow_id (str): ID of the workflow to delete.

    Raises:
        Exception: If the workflow deletion fails.
    """
    url = f"{base_url}/api/v1/workflows/{workflow_id}"
    headers = {"X-N8N-API-KEY": api_key}
    response = requests.delete(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to delete workflow: {response.text}")
    remove_resource_mapping(base_url, 'workflows', workflow_id)

def delete_credential(api_key: str, base_url: str, credential_id: str) -> None:
    """Delete a credential by ID.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        credential_id (str): ID of the credential to delete.

    Raises:
        Exception: If the credential deletion fails.
    """
    url = f"{base_url}/api/v1/credentials/{credential_id}"
    headers = {"X-N8N-API-KEY": api_key}
    response = requests.delete(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to delete credential: {response.text}")
    remove_resource_mapping(base_url, 'credentials', credential_id)

def delete_project(api_key: str, base_url: str, project_id: str) -> None:
    """Delete a project by ID.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.
        project_id (str): ID of the project to delete.

    Raises:
        Exception: If the project deletion fails.
    """
    url = f"{base_url}/api/v1/projects/{project_id}"
    headers = {"X-N8N-API-KEY": api_key}
    response = requests.delete(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to delete project: {response.text}")
    remove_resource_mapping(base_url, 'projects', project_id)

def get_credentials(api_key: str, base_url: str) -> List[Dict]:
    """Get all credentials from the instance.

    Args:
        api_key (str): The API key for authentication.
        base_url (str): The base URL of the n8n instance.

    Returns:
        List[Dict]: List of credential dictionaries.

    Raises:
        Exception: If the credentials retrieval fails.
    """
    url = f"{base_url}/api/v1/credentials"
    headers = {"X-N8N-API-KEY": api_key}
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Failed to get credentials: {response.text}")
    
    return response.json()['data']

def save_resource_mapping(instance_url: str, resource_type: str, resource_id: str, resource_name: str) -> None:
    """Save resource mapping to local storage.

    Args:
        instance_url (str): URL of the n8n instance.
        resource_type (str): Type of resource (workflows, credentials, projects).
        resource_id (str): ID of the resource.
        resource_name (str): Name of the resource.
    """
    storage_file = 'resource_mapping.json'
    try:
        if os.path.exists(storage_file):
            with open(storage_file, 'r') as f:
                mappings = json.load(f)
        else:
            mappings = {}

        if instance_url not in mappings:
            mappings[instance_url] = {
                'workflows': {},
                'credentials': {},
                'projects': {}
            }

        mappings[instance_url][resource_type][resource_id] = resource_name

        with open(storage_file, 'w') as f:
            json.dump(mappings, f, indent=2)

    except Exception as e:
        print_error(f"Failed to save resource mapping: {str(e)}")

def get_instance_resources(instance_url: str) -> Dict:
    """Get all resources for an instance.

    Args:
        instance_url (str): URL of the n8n instance.

    Returns:
        Dict: Dictionary containing all resources for the instance.
    """
    storage_file = 'resource_mapping.json'
    try:
        if os.path.exists(storage_file):
            with open(storage_file, 'r') as f:
                mappings = json.load(f)
                return mappings.get(instance_url, {
                    'workflows': {},
                    'credentials': {},
                    'projects': {}
                })
        return {
            'workflows': {},
            'credentials': {},
            'projects': {}
        }
    except Exception as e:
        print_error(f"Failed to load resource mappings: {str(e)}")
        return {
            'workflows': {},
            'credentials': {},
            'projects': {}
        }

if __name__ == "__main__":
    main()