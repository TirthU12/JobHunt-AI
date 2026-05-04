export const API_URL = "http://127.0.0.1:8000";

export async function parseResume(file: File) {
  const formData = new FormData();
  formData.append("resume", file);
  
  const response = await fetch(`${API_URL}/parse-resume`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to process resume via API.");
  }

  return response.json();
}

export async function searchJobs(payload: any) {
  const response = await fetch(`${API_URL}/search-jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to search jobs via API.");
  }

  return response.json();
}

export async function findContacts(payload: any) {
  const response = await fetch(`${API_URL}/find-contacts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to find contacts via API.");
  }

  return response.json();
}
