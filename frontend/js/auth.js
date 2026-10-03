document.addEventListener("DOMContentLoaded", () => {
	document.getElementById("loginForm")?.addEventListener("submit", handleLogin);
	document.getElementById("registerForm")?.addEventListener("submit", handleRegister);
});

async function submitAuthRequest(url, payload) {
	const response = await fetch(url, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(payload),
	});
	const contentType = response.headers.get("content-type") || "";
	const data = contentType.includes("application/json")
		? await response.json()
		: { message: "The server returned an unexpected response." };
	return { response, data };
}

async function handleLogin(event) {
	event.preventDefault();
	const button = document.getElementById("loginButton");
	const message = document.getElementById("message");
	const email = document.getElementById("email").value.trim();
	const password = document.getElementById("password").value;
	if (!email || !password) return showMessage(message, "Please enter email and password.", true);

	button.disabled = true;
	button.textContent = "Logging in...";
	try {
		const { response, data } = await submitAuthRequest("/api/auth/login", { email, password });
		if (!response.ok) return showMessage(message, data.message || "Login failed.", true);
		showMessage(message, `Login successful. Welcome ${data.user.full_name}!`);
		window.setTimeout(() => {
			window.location.href = data.user.role === "management" ? "/management/dashboard" : "/dashboard";
		}, 500);
	} catch {
		showMessage(message, "Unable to connect to the server.", true);
	} finally {
		button.disabled = false;
		button.textContent = "Login";
	}
}

async function handleRegister(event) {
	event.preventDefault();
	const button = document.getElementById("registerButton");
	const message = document.getElementById("message");
	const fullName = document.getElementById("fullName").value.trim();
	const email = document.getElementById("email").value.trim();
	const password = document.getElementById("password").value;

	if (fullName.length < 2) return showMessage(message, "Please enter your full name.", true);
	if (password.length < 6) return showMessage(message, "Password must contain at least 6 characters.", true);

	button.disabled = true;
	button.textContent = "Creating account...";
	try {
		const { response, data } = await submitAuthRequest("/api/auth/register", {
			full_name: fullName,
			email,
			password,
		});
		if (!response.ok) return showMessage(message, data.message || "Registration failed.", true);
		showMessage(message, "Registration successful");
		window.setTimeout(() => window.location.replace("/login"), 1000);
	} catch {
		showMessage(message, "Unable to connect to the server.", true);
	} finally {
		button.disabled = false;
		button.textContent = "Create Account";
	}
}

function showMessage(element, text, isError = false) {
	if (!element) return;
	element.textContent = text;
	element.dataset.state = isError ? "error" : "success";
}
