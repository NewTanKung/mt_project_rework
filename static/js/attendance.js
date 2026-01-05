/**
 * Attendance Management System
 * จัดการระบบเช็คผู้เข้าร่วมประชุม
 */

let attendanceModal = null;
let attendanceData = {};

// Initialize attendance modal
document.addEventListener('DOMContentLoaded', () => {
    const modalElement = document.getElementById('attendanceModal');
    if (modalElement) {
        attendanceModal = new bootstrap.Modal(modalElement);
    }
});

/**
 * เปิด Modal เช็คผู้เข้าร่วม
 */
async function openAttendanceModal() {
    if (!currentMeeting || !currentMeeting.meeting_id) {
        showAlert('กรุณาเลือกการประชุมก่อน', 'warning');
        return;
    }

    try {
        // ดึงข้อมูลผู้เข้าร่วมและสถานะ attendance
        const response = await fetch(`/api/user/meetings/${currentMeeting.meeting_id}/attendance`);
        const data = await response.json();

        if (data.success) {
            // เตรียมข้อมูล
            attendanceData = {};
            const participants = data.participants || [];

            // ถ้าไม่มีข้อมูลเลย ลอง Initialize
            if (participants.length === 0) {
                console.log('No participants found, initializing...');
                await initializeAttendance();
                return;
            }

            // สร้าง participant cards
            renderAttendanceCards(participants);

            // เปิด modal
            if (attendanceModal) {
                attendanceModal.show();
            }
        } else {
            console.error('API Error:', data.message);
            showAlert('เกิดข้อผิดพลาด: ' + (data.message || 'ไม่สามารถโหลดข้อมูลได้'), 'danger');
        }
    } catch (error) {
        console.error('Error loading attendance:', error);
        showAlert('ไม่สามารถโหลดข้อมูลได้', 'danger');
    }
}

/**
 * Initialize attendance records
 */
async function initializeAttendance() {
    if (!currentMeeting || !currentMeeting.participants) return;

    try {
        const participantIds = currentMeeting.participants.map(p => p.participant_id);

        const response = await fetch(`/api/user/meetings/${currentMeeting.meeting_id}/attendance/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ participant_ids: participantIds })
        });

        const data = await response.json();

        if (data.success) {
            // ลองเปิด modal อีกครั้ง
            await openAttendanceModal();
        } else {
            showAlert(data.message || 'ไม่สามารถสร้างข้อมูลได้', 'danger');
        }
    } catch (error) {
        console.error('Error initializing attendance:', error);
        showAlert('เกิดข้อผิดพลาด', 'danger');
    }
}

/**
 * สร้าง participant cards ใน modal
 */
function renderAttendanceCards(participants) {
    const grid = document.getElementById('attendanceGrid');
    if (!grid) return;

    // ใช้ข้อมูลจาก currentMeeting ถ้าไม่มี participants
    const participantList = participants.length > 0 ? participants : (currentMeeting.participants || []);

    if (participantList.length === 0) {
        grid.innerHTML = '<div class="col-12 text-center text-muted">ไม่มีผู้เข้าร่วม</div>';
        return;
    }

    grid.innerHTML = participantList.map(p => {
        const participantId = p.participant_id;
        const status = p.status || 'not_started';
        const isAbsent = status === 'absent';

        // เก็บสถานะเริ่มต้น
        if (!(participantId in attendanceData)) {
            attendanceData[participantId] = status === 'not_started' ? 'present' : status;
        }

        return `
            <div class="col-md-6 col-lg-4">
                <div class="attendance-card ${isAbsent ? 'absent' : 'present'}" id="attendance-card-${participantId}">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <h6 class="mb-1">${p.participant_name}</h6>
                            <small class="text-muted">
                                <span class="badge bg-info">${p.role || 'สมาชิก'}</span>
                            </small>
                        </div>
                        <button class="btn btn-sm btn-toggle ${isAbsent ? 'btn-danger' : 'btn-success'}" 
                                onclick="toggleAttendance(${participantId})"
                                id="toggle-btn-${participantId}">
                            ${isAbsent ? '❌ ขาด' : '✅ มา'}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Toggle สถานะ present/absent
 */
function toggleAttendance(participantId) {
    const card = document.getElementById(`attendance-card-${participantId}`);
    const button = document.getElementById(`toggle-btn-${participantId}`);

    if (!card || !button) return;

    // สลับสถานะ
    const currentStatus = attendanceData[participantId] || 'present';
    const newStatus = currentStatus === 'present' ? 'absent' : 'present';

    // อัพเดทข้อมูล
    attendanceData[participantId] = newStatus;

    // อัพเดท UI
    if (newStatus === 'absent') {
        card.classList.remove('present');
        card.classList.add('absent');
        button.classList.remove('btn-success');
        button.classList.add('btn-danger');
        button.innerHTML = '❌ ขาด';
    } else {
        card.classList.remove('absent');
        card.classList.add('present');
        button.classList.remove('btn-danger');
        button.classList.add('btn-success');
        button.innerHTML = '✅ มา';
    }
}

/**
 * บันทึก attendance
 */
async function saveAttendance() {
    if (!currentMeeting || !currentMeeting.meeting_id) return;

    try {
        // บันทึกแต่ละคน
        const promises = Object.entries(attendanceData).map(([participantId, status]) => {
            return fetch(`/api/user/meetings/${currentMeeting.meeting_id}/attendance/${participantId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: status })
            });
        });

        await Promise.all(promises);

        // แสดงผล
        const summary = Object.values(attendanceData);
        const presentCount = summary.filter(s => s === 'present').length;
        const absentCount = summary.filter(s => s === 'absent').length;

        showAlert(`บันทึกสำเร็จ! มา ${presentCount} คน, ขาด ${absentCount} คน`, 'success');

        // ปิด modal
        if (attendanceModal) {
            attendanceModal.hide();
        }
    } catch (error) {
        console.error('Error saving attendance:', error);
        showAlert('ไม่สามารถบันทึกได้', 'danger');
    }
}
