# Function Development Specification

> **For students:** This document defines the required structure of your C9 JSON wrapper file
> (e.g. `gc_content.json`). Every field listed under "Required Fields" must be present in your
> `.json` file for full marks on the C9 Wrapper component. The two fields `mcp_name` and
> `seq_params` inside `execution_details` are framework-specific additions used by this starter —
> everything else follows the schema below exactly.

---

## Overview

This document specifies the required structure and authoring instructions for developing functions
compatible with the C9 API. Functions are "Sharable" objects that support CRUD operations,
querying, execution, and GUI display.

---

## JSON Schema for Function Validation

The following JSON schema validates function structure and enforces required fields. Each function
must adhere to this schema to ensure compatibility.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Function",
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "description": "A unique identifier for the function."
    },
    "name": {
      "type": "string",
      "description": "A descriptive name of the function."
    },
    "description": {
      "type": "string",
      "description": "A brief summary of the function's purpose and functionality."
    },
    "type": {
      "type": "string",
      "enum": ["function"],
      "description": "The type of object, which is always 'function'."
    },
    "keywords": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Keywords associated with the function to aid in searchability and categorization."
    },
    "date_created": {
      "type": ["string", "null"],
      "format": "date-time",
      "description": "The creation date and time of the function."
    },
    "date_last_modified": {
      "type": ["string", "null"],
      "format": "date-time",
      "description": "The last modified date and time of the function."
    },
    "inputs": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name":        { "type": "string", "description": "The name of the input parameter." },
          "type":        { "type": "string", "description": "The data type of the input parameter." },
          "description": { "type": "string", "description": "A description of the input parameter." }
        },
        "required": ["name", "type", "description"]
      },
      "description": "A list of input parameters the function accepts."
    },
    "outputs": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "type":        { "type": "string", "description": "The data type of the output." },
          "description": { "type": "string", "description": "A description of the output." }
        },
        "required": ["type", "description"]
      },
      "description": "A list of outputs the function produces."
    },
    "examples": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "input":  { "type": "object", "description": "Example input data for the function." },
          "output": { "type": "object", "description": "Expected output data corresponding to the input." }
        },
        "required": ["input", "output"]
      },
      "description": "Sample inputs and expected outputs for testing and demonstration purposes."
    },
    "execution_details": {
      "type": "object",
      "properties": {
        "language":       { "type": "string", "description": "Programming language used for writing the function." },
        "source":         { "type": "string", "description": "Path to the source file containing the function's code." },
        "initialization": { "type": "string", "description": "Method for initializing the function." },
        "execution":      { "type": "string", "description": "Method for executing the function." },
        "disposal":       { "type": "string", "description": "Method for cleanup after function execution." }
      },
      "required": ["language", "source", "execution"],
      "description": "Details about the execution environment and methodology for the function."
    }
  },
  "required": ["id", "name", "description", "type", "keywords", "inputs", "outputs", "examples", "execution_details"]
}
```

---

## Authoring a Function

1. **Function Naming**: Follow the ID naming convention:
   `org.c9.function.[domain].[term].[specific_identifier].[version]`
   where domain and term align with SKOS, FOAF, BioPortal, or similar ontologies. The
   `specific_identifier` distinguishes each function, and `version` is optional.

2. **Required Fields**:
   - **ID**: A globally unique identifier for the function.
   - **Name**: A concise but descriptive name.
   - **Description**: Briefly outline the function's purpose and functionality.
   - **Type**: Set as `"function"`.
   - **Keywords**: Add relevant keywords for enhanced searchability.
   - **Inputs**: Define each input parameter with `name`, `type`, and `description`.
   - **Outputs**: List each output, including `type` and `description`.
   - **Examples**: Provide sample inputs and expected outputs for testing.
   - **Execution Details**: Specify the programming language, source file, initialization,
     execution, and disposal methods.

3. **Execution Details Structure**:
   - **Language**: Specify the programming language used.
   - **Source**: File path or repository where the function code resides.
   - **Execution**: Main function or method to invoke (`"run"` for this course).
   - **Initialization** *(optional)*: Define if the function requires setup (`"initiate"`).
   - **Disposal** *(optional)*: Specify cleanup if the function uses external resources.

4. **Version Control**: Add version information in the ID for version tracking.

5. **C9 API Operations**:
   Use standard C9 API calls for **Create**, **Read**, **Update**, **Delete**, **Query**,
   **Run**, and **Show** operations. Functions are referenced by ID
   (e.g. `"run": { "function_id": "string" }`) with parameters specified as `args`.

By following this specification and using the schema for validation, each function will be fully
structured, documented, and compatible with C9's API functionality.
