document.querySelectorAll(".chip").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const cedula = btn.dataset.cedula;
    const loading = document.getElementById("loading");
    loading.classList.remove("hidden");
    btn.disabled = true;

    try {
      const res = await fetch(`/api/demo/simular-ingreso?cedula=${cedula}`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await res.text());
      location.reload();
    } catch (e) {
      alert("Error: " + e.message);
    } finally {
      loading.classList.add("hidden");
      btn.disabled = false;
    }
  });
});
