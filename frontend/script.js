const API_BASE = 'http://127.0.0.1:8000';
const qs = (s) => document.querySelector(s);
const cvFile = qs('#cvFile');
const multiCvs = qs('#multiCvs');

function listText(items, fallback = 'None') {
  if (!items || !items.length) return fallback;
  return items.join(', ');
}

function scoreText(value) {
  const number = Number(value || 0);
  return `${number.toFixed(number % 1 === 0 ? 0 : 1)}%`;
}

function showError(message) {
  alert(message || 'Something went wrong. Make sure the FastAPI backend is running.');
}

if (cvFile) {
  cvFile.addEventListener('change', () => {
    qs('#cvFileName').textContent = cvFile.files[0]?.name || 'No file selected';
  });
}

if (multiCvs) {
  multiCvs.addEventListener('change', () => {
    qs('#multiFileName').textContent = multiCvs.files.length
      ? `${multiCvs.files.length} CV files selected`
      : 'No files selected';
  });
}

const seekerForm = qs('#jobseekerForm');
if (seekerForm) {
  seekerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!cvFile.files.length) {
      showError('Please upload a CV PDF first.');
      return;
    }

    const button = seekerForm.querySelector('button[type="submit"]');
    const oldText = button.textContent;
    button.textContent = 'Analyzing CV...';
    button.disabled = true;

    try {
      const selects = seekerForm.querySelectorAll('select');
      const formData = new FormData();
      formData.append('cv', cvFile.files[0]);
      formData.append('work_type', selects[0]?.value || 'Any');
      formData.append('experience', selects[1]?.value || 'Any');

      const response = await fetch(`${API_BASE}/jobseeker/recommend`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not analyze CV.');

      qs('#bestTitle').textContent = data.best_title || 'Best Match';
      qs('#jobScore').textContent = scoreText(data.best_score);
      qs('#jobSummary').textContent = data.summary || 'Your CV analysis is ready.';

      qs('#jobTable').innerHTML = (data.recommendations || []).map((job) => `
        <tr>
          <td>${job.rank}</td>
          <td><b>${job.job_title}</b></td>
          <td>${job.company || 'Unknown'}</td>
          <td><span class="match-pill">${scoreText(job.match_score)}</span></td>
          <td>${job.required_skills || listText(job.matched_skills)}</td>
          <td><span class="danger-pill">${listText(job.missing_skills)}</span></td>
        </tr>
      `).join('');

      qs('#jobResults').classList.remove('hidden');
      qs('#jobResults').scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
      showError(error.message);
    } finally {
      button.textContent = oldText;
      button.disabled = false;
    }
  });
}

const employerForm = qs('#employerForm');
if (employerForm) {
  employerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!multiCvs.files.length) {
      showError('Please upload one or more candidate CV PDFs first.');
      return;
    }

    const button = employerForm.querySelector('button[type="submit"]');
    const oldText = button.textContent;
    button.textContent = 'Ranking Candidates...';
    button.disabled = true;

    try {
      const jobTitle = employerForm.querySelector('input[type="text"]')?.value || '';
      const jobDescription = employerForm.querySelector('textarea')?.value || '';
      const formData = new FormData();
      formData.append('job_title', jobTitle);
      formData.append('job_description', jobDescription);
      [...multiCvs.files].forEach((file) => formData.append('cvs', file));

      const response = await fetch(`${API_BASE}/employer/rank`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not rank candidates.');

      qs('#candidateStatus').textContent = data.status || 'Shortlist ready';
      qs('#candidateScore').textContent = scoreText(data.top_score);
      qs('#candidateSummary').textContent = data.summary || 'Candidate ranking is ready.';

      qs('#candidateList').innerHTML = (data.candidates || []).map((candidate) => `
        <div class="candidate-card">
          <div class="rank-badge">${candidate.rank}</div>
          <div>
            <h3>${candidate.candidate_name} · <span class="match-pill">${scoreText(candidate.match_score)}</span></h3>
            <p><b>Matched:</b> ${listText(candidate.matched_skills)}</p>
            <p><b>Missing:</b> ${listText(candidate.missing_skills)}</p>
          </div>
          <span class="recommend ${candidate.class_name || 'good'}">${candidate.status}</span>
        </div>
      `).join('');

      qs('#candidateResults').classList.remove('hidden');
      qs('#candidateResults').scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
      showError(error.message);
    } finally {
      button.textContent = oldText;
      button.disabled = false;
    }
  });
}
