api_key = st.secrets.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
openai.api_key = api_key

# 🔎 Test if the API key is working
if st.button("🔑 Test OpenAI Key"):
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10
        )
        st.success("✅ API key works! OpenAI replied: " + resp["choices"][0]["message"]["content"])
    except Exception as e:
        st.error(f"❌ API key test failed: {e}")
