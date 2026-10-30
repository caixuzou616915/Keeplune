package app.offlinevault.offline_vault

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    private var pendingResult: MethodChannel.Result? = null
    private var exportSource: File? = null
    private var selectedUri: Uri? = null
    private val worker = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        super.onCreate(savedInstanceState)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "app.offlinevault/security")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "pickFile" -> {
                        if (pendingResult != null) {
                            result.error("busy", "系统文件选择正在进行。", null)
                            return@setMethodCallHandler
                        }
                        val kind = call.argument<String>("kind")
                        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                            addCategory(Intent.CATEGORY_OPENABLE)
                            type = if (kind == "image") "image/*" else "*/*"
                            if (kind != "backup") {
                                putExtra(Intent.EXTRA_MIME_TYPES, if (kind == "image")
                                    arrayOf("image/jpeg", "image/png")
                                else arrayOf("image/jpeg", "image/png", "application/pdf"))
                            }
                            putExtra(Intent.EXTRA_LOCAL_ONLY, true)
                        }
                        pendingResult = result
                        try {
                            startActivityForResult(intent, 8301)
                        } catch (e: android.content.ActivityNotFoundException) {
                            pendingResult = null
                            result.error("picker_unavailable", "系统文件选择器不可用。", null)
                        }
                    }
                    "readSelectedFile" -> {
                        val uri = call.argument<String>("uri")
                        val maximum = call.argument<Int>("maximum")
                        if (uri == null || maximum == null ||
                            maximum !in 1..268435456 || selectedUri?.toString() != uri) {
                            result.error("invalid_selection", "所选文件授权已失效，请重新选择。", null)
                            return@setMethodCallHandler
                        }
                        worker.execute {
                            try {
                                val input = contentResolver.openInputStream(Uri.parse(uri))
                                    ?: throw java.io.IOException("No input stream")
                                val output = ByteArrayOutputStream()
                                input.use { stream ->
                                    val buffer = ByteArray(65536)
                                    var total = 0
                                    while (true) {
                                        val read = stream.read(buffer)
                                        if (read < 0) break
                                        total += read
                                        if (total > maximum) throw java.io.IOException("Size limit exceeded")
                                        output.write(buffer, 0, read)
                                    }
                                }
                                val bytes = output.toByteArray()
                                runOnUiThread { result.success(bytes) }
                            } catch (e: Exception) {
                                runOnUiThread {
                                    result.error("read_failed", "读取失败：文件过大、授权失效或文件不可用。", null)
                                }
                            }
                        }
                    }
                    "exportBackup" -> {
                        if (pendingResult != null) {
                            result.error("busy", "系统文件选择正在进行。", null)
                            return@setMethodCallHandler
                        }
                        val path = call.argument<String>("path")
                        val name = call.argument<String>("name")
                        if (path == null || name == null) {
                            result.error("invalid_export", "无效的备份文件。", null)
                            return@setMethodCallHandler
                        }
                        val source = File(path).canonicalFile
                        if (!source.canonicalPath.startsWith(cacheDir.canonicalPath + File.separator) ||
                            !source.isFile || source.extension != "ovault") {
                            result.error("invalid_export", "只能导出应用生成的加密备份。", null)
                            return@setMethodCallHandler
                        }
                        exportSource = source
                        pendingResult = result
                        try {
                            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                                addCategory(Intent.CATEGORY_OPENABLE)
                                type = "application/octet-stream"
                                putExtra(Intent.EXTRA_TITLE, name)
                                putExtra(Intent.EXTRA_LOCAL_ONLY, true)
                            }, 8302)
                        } catch (e: android.content.ActivityNotFoundException) {
                            pendingResult = null
                            exportSource = null
                            result.error("picker_unavailable", "系统文件保存对话框不可用。", null)
                        }

                    }
                    else -> result.notImplemented()
                }
            }
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    @Deprecated("Activity result API is provided by FlutterActivity")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 8301 && requestCode != 8302) return
        val result = pendingResult ?: return
        pendingResult = null
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            exportSource = null
            result.success(if (requestCode == 8302) false else null)
            return
        }
        if (requestCode == 8301) {
            try {
                var name = "selected-file"
                contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                    ?.use { cursor ->
                        if (cursor.moveToFirst()) name = cursor.getString(0)
                    }
                selectedUri = uri
                result.success(mapOf("uri" to uri.toString(), "name" to name))
            } catch (e: Exception) {
                result.error("selection_failed", "无法读取文件名称或授权。", null)
            }
        } else {
            val source = exportSource
            exportSource = null
            worker.execute {
                try {
                    val input = source?.inputStream()
                        ?: throw java.io.IOException("Missing encrypted backup")
                    input.use { from ->
                        val output = contentResolver.openOutputStream(uri, "wt")
                            ?: throw java.io.IOException("No output stream")
                        output.use { to -> from.copyTo(to) }
                    }
                    runOnUiThread { result.success(true) }
                } catch (e: Exception) {
                    runOnUiThread {
                        result.error("export_failed", "备份写入失败，目标文件可能不完整，请删除后重试。", null)
                    }
                }
            }
        }
    }
}
