const questionInput = document.querySelector("#questionInput");
const answerBox = document.querySelector("#answerBox");
const knowledgeGrid = document.querySelector("#knowledgeGrid");
const searchButton = document.querySelector("#searchButton");
const runPresetButton = document.querySelector("#runPresetButton");
const chipButtons = document.querySelectorAll(".chip-button");
const apiStatus = document.querySelector("#apiStatus");
const docCount = document.querySelector("#docCount");
const answerSourceBadge = document.querySelector("#answerSourceBadge");
const uploadButton = document.querySelector("#uploadButton");
const fileInput = document.querySelector("#fileInput");
const uploadStatus = document.querySelector("#uploadStatus");

function setStatus(text) {
  apiStatus.textContent = text;
}

function setUploadStatus(text) {
  uploadStatus.textContent = text;
}

function renderKnowledgeBase(documents) {
  const visibleDocuments = documents.filter((doc) => doc.show_in_knowledge_base !== false);
  const hiddenPdfCount = documents.filter((doc) => doc.file_type === "pdf").length;

  docCount.textContent = String(visibleDocuments.length);
  knowledgeGrid.innerHTML = visibleDocuments
    .map(
      (doc) => `
        <article class="knowledge-card">
          <div class="knowledge-head">
            <strong>${doc.source}</strong>
            <span class="doc-tag">ID ${doc.id}</span>
          </div>
          <p>${doc.content}</p>
        </article>
      `
    )
    .join("");

  if (hiddenPdfCount > 0) {
    setStatus(`后端已连接。当前有 ${hiddenPdfCount} 条 PDF 片段已入库，但默认不在知识库面板展示。`);
  }
}

async function loadDocuments() {
  setStatus("正在读取后端知识库...");
  const response = await fetch("/api/documents");
  if (!response.ok) {
    throw new Error(`读取知识库失败：HTTP ${response.status}`);
  }
  const data = await response.json();
  renderKnowledgeBase(data.documents);
  setStatus("后端已连接，可以直接提问。");
}

async function askBackend(question) {
  searchButton.disabled = true;
  searchButton.textContent = "后端处理中...";
  answerBox.textContent = "正在执行检索和问答，请稍候...";
  setStatus("后端正在处理当前问题...");

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `请求失败：HTTP ${response.status}`);
    }

    answerBox.textContent = data.answer;
    answerSourceBadge.textContent = data.answer_source === "deepseek" ? "DeepSeek" : "本地回退";

    if (data.llm_error) {
      setStatus(`后端已返回结果，远程模型失败后使用了本地回退：${data.llm_error}`);
    } else {
      setStatus("后端调用成功，当前答案来自 DeepSeek。");
    }
  } catch (error) {
    answerBox.textContent = `后端调用失败：${error.message}`;
    answerSourceBadge.textContent = "请求失败";
    setStatus("无法连接后端服务，请确认 Python 服务已经启动。");
  } finally {
    searchButton.disabled = false;
    searchButton.textContent = "调用后端问答";
  }
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

async function uploadSelectedFile() {
  const file = fileInput.files[0];
  if (!file) {
    setUploadStatus("请先选择一个文件。");
    return;
  }

  uploadButton.disabled = true;
  uploadButton.textContent = "上传中...";
  setUploadStatus(`正在上传 ${file.name} ...`);

  try {
    const buffer = await file.arrayBuffer();
    const contentBase64 = arrayBufferToBase64(buffer);

    const response = await fetch("/api/upload", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        file_name: file.name,
        content_base64: contentBase64,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `上传失败：HTTP ${response.status}`);
    }

    setUploadStatus(data.message);
    await loadDocuments();
    const currentQuestion = questionInput.value.trim();
    if (currentQuestion) {
      await askBackend(currentQuestion);
    }
  } catch (error) {
    setUploadStatus(`上传失败：${error.message}`);
  } finally {
    uploadButton.disabled = false;
    uploadButton.textContent = "上传并加入知识库";
  }
}

searchButton.addEventListener("click", () => {
  const question = questionInput.value.trim() || "请总结这个项目的目标、技术栈和优化点。";
  askBackend(question);
});

runPresetButton.addEventListener("click", () => {
  questionInput.value = "请总结这个项目的目标、技术栈和优化点。";
  askBackend(questionInput.value);
});

chipButtons.forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question;
    askBackend(button.dataset.question);
  });
});

uploadButton.addEventListener("click", uploadSelectedFile);

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) {
    setUploadStatus(`已选择文件：${fileInput.files[0].name}`);
  } else {
    setUploadStatus("支持 txt / pdf / docx。");
  }
});

loadDocuments()
  .then(() => askBackend(questionInput.value))
  .catch((error) => {
    answerBox.textContent = `初始化失败：${error.message}`;
    answerSourceBadge.textContent = "初始化失败";
    setStatus("页面已打开，但后端还没有准备好。");
  });
