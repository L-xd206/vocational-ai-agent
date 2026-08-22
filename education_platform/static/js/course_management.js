(function () {
  var courses = JSON.parse(document.getElementById('initial-courses').textContent || '[]');
  var activeCourse = null;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (value) { var el = document.createElement('div'); el.textContent = value || ''; return el.innerHTML; };

  window.requestCourseJson = async function (url, options) {
    var controller = new AbortController(), timer = setTimeout(function () { controller.abort(); }, 10000);
    try { var response = await fetch(url, Object.assign({}, options || {}, { signal: controller.signal })); var data = await response.json(); if (!response.ok) throw new Error(data.error || '请求失败'); return data; }
    catch (error) { if (error.name === 'AbortError') throw new Error('请求超时，请确认服务已启动后重试'); throw error; }
    finally { clearTimeout(timer); }
  };
  window.renderCourses = function () {
    var key = $('keyword').value.trim().toLowerCase(), type = $('courseTypeFilter').value;
    var items = courses.filter(function (course) { return (!type || course.course_type_code === type) && (course.name + ' ' + course.owner_name).toLowerCase().includes(key); });
    $('rows').innerHTML = items.length ? items.map(function (course) {
      var retry = course.status === 'error' ? '<button class="button text" onclick="retryGeneration(' + course.id + ')">重新生成</button>' : '';
      return '<tr><td class="course-name">' + esc(course.name) + '</td><td>' + esc(course.course_type) + '</td><td>' + course.total_hours + '</td><td>' + course.credits + '</td><td>' + esc(course.organization) + '</td><td class="owner">' + esc(course.owner_name) + '</td><td>' + esc(course.status_label) + '</td><td><button class="button text" onclick="openCourseEditor(' + course.id + ')">编辑</button>' + retry + '</td></tr>';
    }).join('') : '<tr><td colspan="8" class="empty">暂无符合条件的课程</td></tr>';
  };
  window.resetFilters = function () { $('keyword').value = ''; $('courseTypeFilter').value = ''; window.renderCourses(); };
  window.showNewCourseMessage = function () { alert('课程应由正式能力树下发后自动生成，暂不支持手动新增空课程。'); };
  window.openCourseEditor = async function (courseId) {
    activeCourse = courses.find(function (course) { return course.id === courseId; }); if (!activeCourse) return;
    $('courseName').value = activeCourse.name; $('courseType').value = activeCourse.course_type_code; $('courseHours').value = activeCourse.total_hours; $('courseCredits').value = activeCourse.credits; $('courseOrganization').value = activeCourse.organization;
    $('courseOwner').innerHTML = '<option value="">正在加载负责人账号…</option>'; $('courseModal').classList.add('open');
    try { var data = await window.requestCourseJson('/api/curriculum/owner-candidates?tree_id=' + activeCourse.id); var owners = data.users || []; $('courseOwner').innerHTML = owners.length ? owners.map(function (owner) { return '<option value="' + owner.id + '"' + (owner.id === activeCourse.owner_id ? ' selected' : '') + '>' + esc(owner.name) + '（' + esc(owner.username) + '）</option>'; }).join('') : '<option value="">当前学院暂无课程负责人账号</option>'; }
    catch (error) { $('courseOwner').innerHTML = '<option value="">' + esc(error.message) + '</option>'; }
  };
  window.closeCourseEditor = function () { $('courseModal').classList.remove('open'); activeCourse = null; };
  window.saveCourseEditor = async function () {
    if (!activeCourse) return; var ownerId = $('courseOwner').value; if (!ownerId) return alert('请为课程选择负责人');
    try { await window.requestCourseJson('/api/curriculum/manage/' + activeCourse.id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: $('courseName').value, course_type: $('courseType').value, total_hours: Number($('courseHours').value), credits: $('courseCredits').value, owner_id: Number(ownerId) }) }); window.closeCourseEditor(); await window.reloadCourses(); }
    catch (error) { alert(error.message); }
  };
  window.reloadCourses = async function () { try { var data = await window.requestCourseJson('/api/curriculum/manage'); courses = data.courses || []; window.renderCourses(); } catch (error) { $('rows').innerHTML = '<tr><td colspan="8" class="empty">' + esc(error.message) + '</td></tr>'; } };
  window.retryGeneration = async function (treeId) { if (!window.confirm('将重新调用 AI 匹配教材并生成学习任务树，确认继续？')) return; try { await window.requestCourseJson('/api/curriculum/' + treeId + '/ai-generate', { method: 'POST' }); await window.reloadCourses(); alert('已开始后台生成，可稍后刷新查看结果。'); } catch (error) { alert(error.message); } };
}());
