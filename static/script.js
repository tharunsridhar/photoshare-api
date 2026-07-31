const API_BASE = "";

function getToken() { return localStorage.getItem("token"); }
function setToken(t) { localStorage.setItem("token", t); }
function clearToken() { localStorage.removeItem("token"); }

function showAuthTab(tab) {
    document.getElementById("loginTab").classList.toggle("hidden", tab !== "login");
    document.getElementById("registerTab").classList.toggle("hidden", tab !== "register");
    document.getElementById("tabLoginBtn").classList.toggle("active", tab === "login");
    document.getElementById("tabRegisterBtn").classList.toggle("active", tab === "register");
}

function initials(email) {
    return (email || "?").trim()[0]?.toUpperCase() || "?";
}

async function register() {
    const email = document.getElementById("registerEmail").value;
    const password = document.getElementById("registerPassword").value;
    const errorEl = document.getElementById("registerError");
    errorEl.textContent = "";
    try {
        const res = await fetch(`${API_BASE}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
            const err = await res.json();
            errorEl.textContent = err.detail ? JSON.stringify(err.detail) : "Registration failed";
            return;
        }
        showAuthTab("login");
        document.getElementById("loginEmail").value = email;
    } catch (e) {
        errorEl.textContent = "Could not reach the server";
    }
}

async function login() {
    const email = document.getElementById("loginEmail").value;
    const password = document.getElementById("loginPassword").value;
    const errorEl = document.getElementById("loginError");
    errorEl.textContent = "";
    try {
        const body = new URLSearchParams();
        body.set("username", email);
        body.set("password", password);
        const res = await fetch(`${API_BASE}/auth/jwt/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body,
        });
        if (!res.ok) {
            errorEl.textContent = "Invalid email or password";
            return;
        }
        const data = await res.json();
        setToken(data.access_token);
        await enterApp();
    } catch (e) {
        errorEl.textContent = "Could not reach the server";
    }
}

function logout() {
    clearToken();
    document.getElementById("appView").classList.add("hidden");
    document.getElementById("userBox").classList.add("hidden");
    document.getElementById("authView").classList.remove("hidden");
}

async function enterApp() {
    const res = await fetch(`${API_BASE}/users/me`, {
        headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) {
        logout();
        return;
    }
    const me = await res.json();
    document.getElementById("whoami").textContent = me.email;
    document.getElementById("whoamiAvatar").textContent = initials(me.email);
    document.getElementById("authView").classList.add("hidden");
    document.getElementById("userBox").classList.remove("hidden");
    document.getElementById("appView").classList.remove("hidden");
    await loadFeed();
}

async function upload() {
    const fileEl = document.getElementById("fileInput");
    const caption = document.getElementById("captionInput").value;
    const errorEl = document.getElementById("uploadError");
    errorEl.textContent = "";
    if (!fileEl.files.length) {
        errorEl.textContent = "Pick a file first";
        return;
    }
    const form = new FormData();
    form.append("file", fileEl.files[0]);
    form.append("caption", caption);
    form.append("content", caption);
    try {
        const res = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            headers: { Authorization: `Bearer ${getToken()}` },
            body: form,
        });
        if (!res.ok) {
            const err = await res.json();
            errorEl.textContent = err.detail || "Upload failed";
            return;
        }
        fileEl.value = "";
        document.getElementById("captionInput").value = "";
        await loadFeed();
    } catch (e) {
        errorEl.textContent = "Could not reach the server";
    }
}

async function loadFeed() {
    const res = await fetch(`${API_BASE}/feed`, {
        headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) return;
    const data = await res.json();
    const feedEl = document.getElementById("feed");
    feedEl.innerHTML = "";

    if (!data.posts.length) {
        feedEl.innerHTML = `<p class="feed-empty">No posts yet — share the first one.</p>`;
        return;
    }

    for (const post of data.posts) {
        const div = document.createElement("div");
        div.className = "post card";
        const media = post.file_type === "video"
            ? `<video src="${post.url}" controls></video>`
            : `<img src="${post.url}" alt="post image">`;
        const deleteBtn = post.is_owner
            ? `<button class="btn btn-danger delete-btn" data-post-id="${post.id}">Delete</button>`
            : "";
        div.innerHTML = `
            <div class="media-wrap">${media}</div>
            <div class="post-body">
                <p class="caption">${post.caption ?? ""}</p>
                <div class="meta">
                    <span class="meta-left">
                        <span class="avatar">${initials(post.email)}</span>
                        ${post.email}
                    </span>
                    <span>${new Date(post.created_at).toLocaleString()}</span>
                </div>
                ${deleteBtn}
            </div>
        `;
        const delBtn = div.querySelector(".delete-btn");
        if (delBtn) delBtn.addEventListener("click", () => deletePost(post.id));
        feedEl.appendChild(div);
    }
}

async function deletePost(postId) {
    const res = await fetch(`${API_BASE}/posts/${postId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (res.ok) await loadFeed();
}

document.getElementById("tabLoginBtn").addEventListener("click", () => showAuthTab("login"));
document.getElementById("tabRegisterBtn").addEventListener("click", () => showAuthTab("register"));
document.getElementById("loginBtn").addEventListener("click", login);
document.getElementById("registerBtn").addEventListener("click", register);
document.getElementById("logoutBtn").addEventListener("click", logout);
document.getElementById("uploadBtn").addEventListener("click", upload);
document.getElementById("fileInput").addEventListener("change", (e) => {
    const text = document.getElementById("fileDropText");
    text.textContent = e.target.files[0]?.name || "Choose an image or video";
});

if (getToken()) {
    enterApp();
}
