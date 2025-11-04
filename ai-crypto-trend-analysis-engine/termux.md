# 📱 Running the AI Crypto Trend Analyzer on Android with Termux

This guide provides a complete walkthrough for setting up and running the AI Crypto Trend Analyzer project on an Android device using the [Termux](https://termux.dev/en/) terminal emulator. This allows you to perform real-time market analysis directly from your phone or tablet.

## Prerequisites

-   An Android device.
-   The Termux application installed. It is **highly recommended** to install Termux from [F-Droid](https://f-droid.org/en/packages/com.termux/) to ensure you get the latest updates.

---

## Step 1: Initial Termux Setup

First, we need to make sure Termux and its packages are up to date.

1.  Open the Termux app.
2.  Run the following command to update and upgrade all base packages. You may be prompted to approve changes several times; it's generally safe to accept the default options by pressing `Enter`.

```bash
pkg update && pkg upgrade
```

## Step 2: Install Dependencies

We need to install a few essential tools: `git` to download the project files, `nodejs-lts` to run the JavaScript environment and build tool, and `nano` to easily edit files.

```bash
pkg install git nodejs-lts nano
```

## Step 3: Get the Project Files

Now, let's download the project source code using `git`.

1.  Navigate to your home directory (Termux usually starts here).
2.  Clone the project repository. For this guide, we'll assume the project files are placed in a directory named `ai-crypto-analyzer`.
3.  Navigate into the created project directory:

```bash
cd ai-crypto-analyzer
```

## Step 4: Configure the Gemini API Key (Crucial Step)

We will use a standard `.env` file to securely store your API key.

1.  **Get Your Key**: Make sure you have your Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

2.  **Create the `.env` file**: Use the `nano` text editor to create and edit the environment file:

    ```bash
    nano .env
    ```

3.  **Add Your Key**: In the `nano` editor, paste the following line, replacing `"YOUR_GEMINI_API_KEY_HERE"` with your actual key:
    ```
    VITE_API_KEY="YOUR_GEMINI_API_KEY_HERE"
    ```

4.  **Save and Exit**:
    -   Press `Ctrl` + `O` (the letter 'O', not zero) to write the changes.
    -   Press `Enter` to confirm the filename.
    -   Press `Ctrl` + `X` to exit `nano`.

## Step 5: Install Project Dependencies and Run

Now we will install the project's dependencies and start the development server.

1.  Install the project's `node_modules` using `npm`:

    ```bash
    npm install
    ```

2.  Start the Vite development server:

    ```bash
    npm start
    ```

3.  The server will start and display a list of available network addresses. The one you need for your mobile browser is the `Network` address, which will look something like `http://192.168.1.100:5173`.

## Step 6: Access the Dashboard

You're all set!

1.  Open a web browser on your Android device (e.g., Chrome, Firefox).
2.  Navigate to the **Network address** provided by Vite in the previous step.
3.  The AI Crypto Trend Analyzer dashboard should load and be fully functional.

---

### Conclusion

Congratulations! You now have a complete, self-hosted version of the AI Crypto Trend Analyzer running on your Android device. You can now perform market analysis anytime, anywhere.