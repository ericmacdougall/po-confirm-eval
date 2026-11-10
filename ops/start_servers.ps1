# Starts two localhost-only llama.cpp servers on the GPU host (RTX 3090). Detached; logs under C:\lab-e.
$exe = "C:\lab-e\llama-server.exe"
Start-Process -WindowStyle Hidden -FilePath $exe -RedirectStandardError "C:\lab-e\srv7.err" -RedirectStandardOutput "C:\lab-e\srv7.out" -ArgumentList @("-m","C:\lab-e\models\qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf","--host","127.0.0.1","--port","8081","-ngl","99","-c","16384","-np","4")
Start-Process -WindowStyle Hidden -FilePath $exe -RedirectStandardError "C:\lab-e\srv3.err" -RedirectStandardOutput "C:\lab-e\srv3.out" -ArgumentList @("-m","C:\lab-e\models\qwen2.5-3b-instruct-q4_k_m.gguf","--host","127.0.0.1","--port","8082","-ngl","99","-c","16384","-np","4")
