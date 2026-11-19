"""
مسئله‌ی نویسندگان و خوانندگان (Readers-Writers) با چهار روش همگام‌سازی:
  1) الگوریتم پترسون (تعمیم N-نخی: Filter Lock)
  2) الگوریتم دکر (فقط ۲ نخ)
  3) سمافور
  4) مانیتور (threading.Condition)

قوانین مسئله:
  - چند خواننده می‌توانند هم‌زمان بخوانند.
  - نویسنده باید انحصاری بنویسد (نه خواننده‌ی هم‌زمان، نه نویسنده‌ی دیگر).
"""
import threading
import time
import random


# ======================================================================
# ابزار بررسی درستی (فقط برای تست؛ جزو الگوریتم‌ها نیست)
# ======================================================================
class Checker:
    def __init__(self):
        self._l = threading.Lock()
        self.readers = 0
        self.writers = 0
        self.violations = 0

    def enter_read(self):
        with self._l:
            self.readers += 1
            if self.writers > 0:
                self.violations += 1

    def exit_read(self):
        with self._l:
            self.readers -= 1

    def enter_write(self):
        with self._l:
            self.writers += 1
            if self.writers > 1 or self.readers > 0:
                self.violations += 1

    def exit_write(self):
        with self._l:
            self.writers -= 1


# ======================================================================
# ۱) پترسون (تعمیم N-پردازه‌ای = Filter Lock؛ برای N=2 همان پترسون کلاسیک)
# ======================================================================
class PetersonLock:
    def __init__(self, n):
        self.n = n
        self.level = [0] * n          # سطحی که هر نخ در آن است
        self.victim = [-1] * n        # قربانی هر سطح

    def acquire(self, i):
        for L in range(1, self.n):
            self.level[i] = L
            self.victim[L] = i
            # صبر کن تا نخ دیگری هم‌سطح یا بالاتر هست و من قربانی‌ام
            while self.victim[L] == i and any(
                self.level[k] >= L for k in range(self.n) if k != i
            ):
                time.sleep(0)

    def release(self, i):
        self.level[i] = 0


# ======================================================================
# ۲) دکر (فقط برای دو نخ با شناسه‌ی 0 و 1)
# ======================================================================
class DekkerLock:
    def __init__(self):
        self.wants = [False, False]
        self.turn = 0

    def acquire(self, i):
        j = 1 - i
        self.wants[i] = True
        while self.wants[j]:
            if self.turn == j:
                self.wants[i] = False
                while self.turn == j:
                    time.sleep(0)
                self.wants[i] = True

    def release(self, i):
        self.turn = 1 - i
        self.wants[i] = False


# ----------------------------------------------------------------------
# حل مسئله‌ی RW بر پایه‌ی یک قفل انحصاری (پترسون یا دکر)
# قفل فقط از وضعیت مشترک (readers, writing) محافظت می‌کند و انتظار
# اصلی خارج از ناحیه‌ی بحرانی انجام می‌شود (تا آزادسازی توسط نخ دیگر لازم نشود).
# ----------------------------------------------------------------------
class SpinLockRW:
    def __init__(self, lock):
        self.lock = lock
        self.readers = 0
        self.writing = False

    def start_read(self, tid):
        while True:
            self.lock.acquire(tid)
            if not self.writing:
                self.readers += 1
                self.lock.release(tid)
                return
            self.lock.release(tid)
            time.sleep(0)

    def end_read(self, tid):
        self.lock.acquire(tid)
        self.readers -= 1
        self.lock.release(tid)

    def start_write(self, tid):
        while True:
            self.lock.acquire(tid)
            if not self.writing and self.readers == 0:
                self.writing = True
                self.lock.release(tid)
                return
            self.lock.release(tid)
            time.sleep(0)

    def end_write(self, tid):
        self.lock.acquire(tid)
        self.writing = False
        self.lock.release(tid)


# ======================================================================
# ۳) سمافور (اولویت با خوانندگان)
# ======================================================================
class SemaphoreRW:
    def __init__(self):
        self.mutex = threading.Semaphore(1)   # محافظ read_count
        self.rw = threading.Semaphore(1)      # دسترسی انحصاری به داده
        self.read_count = 0

    def start_read(self, tid=None):
        self.mutex.acquire()
        self.read_count += 1
        if self.read_count == 1:              # اولین خواننده، نویسنده‌ها را قفل می‌کند
            self.rw.acquire()
        self.mutex.release()

    def end_read(self, tid=None):
        self.mutex.acquire()
        self.read_count -= 1
        if self.read_count == 0:              # آخرین خواننده، قفل را آزاد می‌کند
            self.rw.release()
        self.mutex.release()

    def start_write(self, tid=None):
        self.rw.acquire()

    def end_write(self, tid=None):
        self.rw.release()


# ======================================================================
# ۴) مانیتور (اولویت با نویسندگان برای جلوگیری از گرسنگی آن‌ها)
# ======================================================================
class MonitorRW:
    def __init__(self):
        self.cond = threading.Condition()     # قفل + متغیر شرطی
        self.readers = 0
        self.writing = False
        self.waiting_writers = 0

    def start_read(self, tid=None):
        with self.cond:
            while self.writing or self.waiting_writers > 0:
                self.cond.wait()
            self.readers += 1

    def end_read(self, tid=None):
        with self.cond:
            self.readers -= 1
            if self.readers == 0:
                self.cond.notify_all()

    def start_write(self, tid=None):
        with self.cond:
            self.waiting_writers += 1
            while self.writing or self.readers > 0:
                self.cond.wait()
            self.waiting_writers -= 1
            self.writing = True

    def end_write(self, tid=None):
        with self.cond:
            self.writing = False
            self.cond.notify_all()


# ======================================================================
# نخ‌های خواننده و نویسنده + اجرای آزمایشی
# ======================================================================
def reader(rw, tid, chk, data, rounds):
    for _ in range(rounds):
        rw.start_read(tid)
        chk.enter_read()
        _ = data["value"]
        time.sleep(random.uniform(0, 0.002))
        chk.exit_read()
        rw.end_read(tid)
        time.sleep(random.uniform(0, 0.002))


def writer(rw, tid, chk, data, rounds):
    for _ in range(rounds):
        rw.start_write(tid)
        chk.enter_write()
        data["value"] += 1
        time.sleep(random.uniform(0, 0.002))
        chk.exit_write()
        rw.end_write(tid)
        time.sleep(random.uniform(0, 0.002))


def run(name, rw, n_readers, n_writers, rounds=15):
    chk = Checker()
    data = {"value": 0}
    threads = []
    tid = 0
    for _ in range(n_readers):
        threads.append(threading.Thread(target=reader, args=(rw, tid, chk, data, rounds)))
        tid += 1
    for _ in range(n_writers):
        threads.append(threading.Thread(target=writer, args=(rw, tid, chk, data, rounds)))
        tid += 1
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = chk.violations == 0 and data["value"] == n_writers * rounds
    print(f"{name:<12} خواننده={n_readers} نویسنده={n_writers} "
          f"مقدار نهایی={data['value']} تخلف={chk.violations} -> {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    # پترسون N-نخی: ۳ خواننده + ۲ نویسنده
    run("Peterson", SpinLockRW(PetersonLock(5)), 3, 2)
    # دکر فقط دو نخ: ۱ خواننده + ۱ نویسنده
    run("Dekker", SpinLockRW(DekkerLock()), 1, 1)
    run("Semaphore", SemaphoreRW(), 4, 2)
    run("Monitor", MonitorRW(), 4, 2)
