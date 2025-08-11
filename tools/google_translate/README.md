# Overview

The Google Translate Tool allows users to translate text from one language to another seamlessly. It leverages Google's robust translation capabilities to provide accurate and efficient translations. This tool is designed for developers and teams who need to integrate translation functionality into their workflows or applications.

# Configure

1. Install Google Translate from Dify Marketplace.
   ![](_assets/google_translate_install.PNG)
2. Add Google Translate to your workflow.
3. Fill in variables.

   ![](_assets/google_translate_configure.png)

* **Text Content** (Required): This is the string input that needs to be translated. You can type or insert the variable directly into the provided field.
* **Destination Language**: This is a required field where you specify the target language for translation (e.g., "English," "Spanish," "French"). Ensure the name of the language matches Google's supported languages.

![](_assets/google_translate_test.PNG)

## Custom destination language

If you select **Custom** as the Destination Language, an additional field called **Custom destination language** will appear:

![](_assets/google_translate_configure_custom.png)

* **Custom destination language:** Enter a language code or variable (e.g. `en`, `es`, `fr`) if you selected Custom above.

**Example:**
To translate text into Bangla, select Custom for Destination Language, then either enter `bn` directly or pass a `variable` containing the value bn in the Custom destination language field.