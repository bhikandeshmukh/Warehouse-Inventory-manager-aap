# Keep Kotlinx Serialization classes
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keep,includedescriptorclasses class com.warehouse.inventory.**$$serializer { *; }
-keepclassmembers class com.warehouse.inventory.** {
    *** Companion;
}
-keepclasseswithmembers class com.warehouse.inventory.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Apache POI
-dontwarn org.apache.poi.**
-dontwarn org.apache.xmlbeans.**
-dontwarn org.openxmlformats.**
-dontwarn org.etsi.uri.**
-dontwarn org.w3.x2000.**
-keep class org.apache.poi.** { *; }

# Ktor
-dontwarn io.ktor.**
-dontwarn org.slf4j.**
