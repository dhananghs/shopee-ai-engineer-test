## 1. Describe differences between REST API, MCP in the context of AI.

REST API is a way for applications to communicate with each other over the internet, the thing being called is usually a service. In the context of AI, in order for AI to use a service, we need to dictate of how to use the service, every single service need a written instruction or documentation passes to the AI. MCP on the other hand, is a newer protocol that standardizes how AI uses services. Instead a custom instruction for each services or tools, MCP provide the service or tool's description in a machine readable way. The AI will discover and decide which tools to use and how.

## 2. How REST API, MCP, can improve the AI use case.

AI models are frozen in time (dependent on the data they were trained on) and cannot access the information from the outside. REST API and MCP help AI to tackle these issues. With them, it can be granted access to real time information, perform actions, and unlock many other possibilities.

## 3. How do you ensure that your AI agent answers correctly?

Few things can be done.

- Force the AI to answer by retrieving real documents or data, so it won't just recall or construct the answer just based on its memory.
- Ask it to always provide the citation to its answer
- Use second AI model to act as judge for the first AI model's answer
- Build a benchmark so we can measure the AI performance on our specific tasks

## 4. Describe what can you do with Docker / Containerize environment in the context of AI

- Serving models
- Building a scalable system
- Isolation for safety
- Making pipelines
- etc

## 5. How do you finetune the LLM model from raw ?

- Define the objective
- Choose the model
- Choose a fine-tuning method (like LoRA or QLoRA)
- Collect enough data, it can be documents, chats, or q&a pairs
- Prepare the data by cleaning, filtering, and converting it to the training format
- Split the data into training and validation sets, for benchmarking
- Train the model on prepared data
- Evaluate
- Iterate
