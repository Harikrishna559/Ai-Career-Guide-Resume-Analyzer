const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const dashboardSource = fs.readFileSync(
  path.join(__dirname, '..', 'static', 'js', 'dashboard.js'),
  'utf8',
);

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.attributes = {};
    this.style = {};
    this.listeners = {};
    this.textContent = '';
    this.className = '';
    this.hidden = false;
  }

  append(...elements) {
    this.children.push(...elements);
  }

  appendChild(element) {
    this.children.push(element);
    return element;
  }

  replaceChildren(...elements) {
    this.children = elements;
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  addEventListener(name, callback) {
    this.listeners[name] = callback;
  }
}

function startDashboard(initialData = {}) {
  const data = new Map(Object.entries(initialData));
  const elements = {
    'dashboard-summary': new Element('div'),
    'clear-saved-data': new Element('button'),
    'clear-data-status': new Element('p'),
  };
  const listeners = {};
  const document = {
    addEventListener(name, callback) {
      listeners[name] = callback;
    },
    createElement(tagName) {
      return new Element(tagName);
    },
    getElementById(id) {
      return elements[id] || null;
    },
  };
  const window = {
    appStorage: {
      getJSON(key, fallback) {
        const value = data.get(key);
        if (value === undefined) return fallback;
        try {
          return JSON.parse(value);
        } catch {
          return fallback;
        }
      },
      removeKeys(keys) {
        keys.forEach(key => data.delete(key));
        return true;
      },
    },
    confirm() {
      return true;
    },
  };

  vm.runInNewContext(dashboardSource, { document, window, Date, Intl, Number });
  listeners.DOMContentLoaded();

  return {
    clearButton: elements['clear-saved-data'],
    clearStatus: elements['clear-data-status'],
    data,
    summary: elements['dashboard-summary'],
  };
}

function getMetric(summary, title) {
  const card = summary.children.find(child => child.children[0].textContent === title);
  assert.ok(card, `Expected dashboard card: ${title}`);
  return card.children[1].textContent;
}

test('empty dashboard uses clear no-data states instead of scores', () => {
  const { summary } = startDashboard();

  assert.equal(getMetric(summary, 'Career Readiness'), 'Start a career plan');
  assert.equal(getMetric(summary, 'ATS Compatibility Estimate'), 'Not analyzed yet');
  assert.equal(getMetric(summary, 'JD Keyword Estimate'), 'No match yet');
  assert.equal(getMetric(summary, 'Roadmap Progress'), 'Start a career plan');
  assert.equal(getMetric(summary, 'Interview Score'), 'Complete an interview');
});

test('partial dashboard data shows the real career result only', () => {
  const { summary } = startDashboard({
    careerGuideResults: JSON.stringify({
      success: true,
      readiness_score: 73,
      roadmap: [{ day: 1 }, { day: 2 }],
    }),
    roadmapProgress: JSON.stringify({ roadmap_1: true }),
  });

  assert.equal(getMetric(summary, 'Career Readiness'), '73/100');
  assert.equal(getMetric(summary, 'Roadmap Progress'), '50%');
  assert.equal(getMetric(summary, 'ATS Compatibility Estimate'), 'Not analyzed yet');
  assert.equal(getMetric(summary, 'JD Keyword Estimate'), 'No match yet');
  assert.equal(getMetric(summary, 'Interview Score'), 'Complete an interview');
});

test('valid saved data renders actual values and a recorded practice date', () => {
  const { summary } = startDashboard({
    careerGuideResults: JSON.stringify({ success: true, readiness_score: 72, roadmap: [{ day: 1 }] }),
    resumeAnalysisResults: JSON.stringify({ success: true, ats_score: 86 }),
    jobDescriptionResults: JSON.stringify({ success: true, match_score: 91 }),
    interviewReport: JSON.stringify({ overall_score: 88, last_practice: '2026-10-08T05:00:00.000Z' }),
    roadmapProgress: JSON.stringify({ roadmap_1: true }),
  });

  assert.equal(getMetric(summary, 'Career Readiness'), '72/100');
  assert.equal(getMetric(summary, 'ATS Compatibility Estimate'), '86/100');
  assert.equal(getMetric(summary, 'JD Keyword Estimate'), '91/100');
  assert.equal(getMetric(summary, 'Roadmap Progress'), '100%');
  assert.equal(getMetric(summary, 'Interview Score'), '88/100');
  const practiceDetail = summary.children[4].children.find(child => child.tagName === 'p').textContent;
  assert.match(practiceDetail, /Last practice:/);
  assert.doesNotMatch(practiceDetail, /Not recorded/);
});

test('malformed, invalid, and cleared data never leave old metrics visible', () => {
  const dashboard = startDashboard({
    careerGuideResults: '{invalid json',
    resumeAnalysisResults: JSON.stringify({ success: true, ats_score: 150 }),
    jobDescriptionResults: JSON.stringify([]),
    interviewReport: JSON.stringify({ overall_score: '78', last_practice: 'Today' }),
    roadmapProgress: JSON.stringify([]),
  });

  assert.equal(getMetric(dashboard.summary, 'Career Readiness'), 'Start a career plan');
  assert.equal(getMetric(dashboard.summary, 'ATS Compatibility Estimate'), 'Not analyzed yet');
  assert.equal(getMetric(dashboard.summary, 'JD Keyword Estimate'), 'No match yet');
  assert.equal(getMetric(dashboard.summary, 'Interview Score'), 'Complete an interview');

  dashboard.clearButton.listeners.click();
  assert.equal(getMetric(dashboard.summary, 'ATS Compatibility Estimate'), 'Not analyzed yet');
  assert.equal(getMetric(dashboard.summary, 'Interview Score'), 'Complete an interview');
  assert.equal(dashboard.clearStatus.textContent, 'Saved application data has been cleared from this browser.');
});
