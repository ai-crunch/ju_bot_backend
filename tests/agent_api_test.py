import requests
import json
import os

# Define the API endpoint URL
# You'll need to replace 'http://127.0.0.1:8000' with your actual server address and port
API_URL = "http://127.0.0.1:8000/api/agent"

# Define the headers for the request
headers = {"Content-Type": "application/json"}


def run_chat_test(messages):
    """
    Sends a POST request to the chat API endpoint and prints the response.

    Args:
        messages (list): A list of message dictionaries.
    """
    try:
        # Create the JSON payload from the messages
        payload = {"messages": messages}

        print("Sending request to API...")
        print(f"Payload: {json.dumps(payload, indent=2)}")

        # Send the POST request
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload))

        # Check for a successful response (status code 200)
        if response.status_code == 200:
            print("\nSuccessfully received a response!")
            data = response.json()
            print(f"Response: {data.get('response')}")

            sources = data.get("sources", [])
            if sources:
                print("\nSources:")
                for i, source in enumerate(sources):
                    print(f"  - Source {i+1}:")
                    print(f"    Text: {source.get('text')}")
                    print(f"    File Path: {source.get('file_path')}")
            else:
                print("\nNo sources were provided in the response.")
        else:
            print(f"\nError: API returned status code {response.status_code}")
            print(f"Response body: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"\nAn error occurred while connecting to the API: {e}")
    except json.JSONDecodeError:
        print("\nError: Could not decode JSON from the response.")


if __name__ == "__main__":
    # --- Test Cases ---
    print("--- Running Test Case 1: Simple Greeting ---")
    run_chat_test([{"role": "user", "content": "Hello"}])

    print("\n" + "=" * 50 + "\n")

    print("--- Running Test Case 2: University-related question ---")
    run_chat_test(
        [
            {
                "role": "user",
                "content": "What are the admission requirements for graduate studies at the University of Jordan?",
            }
        ]
    )

    print("\n" + "=" * 50 + "\n")

    print("--- Running Test Case 3: Non-university question ---")
    run_chat_test([{"role": "user", "content": "Who invented the telephone?"}])

    print("\n" + "=" * 50 + "\n")

    print("--- Running Test Case 4: Multi-turn conversation ---")
    run_chat_test(
        [
            {
                "role": "user",
                "content": "What are the office hours for the registration department?",
            },
            {
                "role": "assistant",
                "content": "I am not sure. I need to check the documents.",
            },
            {"role": "user", "content": "Could you try to find them?"},
        ]
    )
