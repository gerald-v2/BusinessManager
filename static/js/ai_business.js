async function askAI() {

    const input = document.getElementById("message");

    const messages = document.getElementById("messages");

    const message = input.value.trim();

    if (!message) {
        return;
    }


    // Display user's message

    messages.innerHTML += `
        <div class="message user-message">

            <strong>You</strong>

            <p>${message}</p>

        </div>
    `;


    input.value = "";


    // Temporary loading message

    const loading = document.createElement("div");

    loading.className = "message ai-message";

    loading.innerHTML = `
        <strong>AI Assistant</strong>
        <p>Thinking...</p>
    `;

    messages.appendChild(loading);


    try {

        const response = await fetch(
    `/biz/${encodeURIComponent(biz)}/ai-business/ask`,
    {
        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({
            message: message
        })
    }
);


        const data = await response.json();


        loading.remove();


        if (data.error) {

            messages.innerHTML += `
                <div class="message ai-message">

                    <strong>Error</strong>

                    <p>${data.error}</p>

                </div>
            `;

            return;
        }


        messages.innerHTML += `
            <div class="message ai-message">

                <strong>AI Assistant</strong>

                <p>${data.response}</p>

            </div>
        `;


    } catch (error) {

        loading.remove();

        messages.innerHTML += `
            <div class="message ai-message">

                <strong>Error</strong>

                <p>
                    Something went wrong connecting
                    to the server.
                </p>

            </div>
        `;
    }
}