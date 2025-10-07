import requests
import json
import os

# Define the API endpoint URL
# You'll need to replace 'http://127.0.0.1:8000' with your actual server address and port
API_URL = "http://127.0.0.1:8000/api/agent"

# Define the headers for the request
headers = {"Content-Type": "application/json"}


def test_chat_api(messages):
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


# --- Test Cases ---
# Each test case is a list of messages representing a conversation.

# Test Case 1: Simple greeting
print("--- Running Test Case 1: Simple Greeting ---")
test_chat_api([{"role": "user", "content": "Hello"}])

print("\n" + "=" * 50 + "\n")

# Test Case 2: A question about the university
print("--- Running Test Case 2: University-related question ---")
test_chat_api(
    [
        {
            "role": "user",
            "content": "What are the admission requirements for graduate studies at the University of Jordan?",
        }
    ]
)

print("\n" + "=" * 50 + "\n")

# Test Case 3: A question not related to the university
print("--- Running Test Case 3: Non-university question ---")
test_chat_api([{"role": "user", "content": "Who invented the telephone?"}])

print("\n" + "=" * 50 + "\n")

# Test Case 4: A more complex, multi-turn conversation
print("--- Running Test Case 4: Multi-turn conversation ---")
test_chat_api(
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
