/*
 * Singleton_B.java
 * Thread-safe Singleton — same GoF pattern, different class/variable names.
 * Tests the merger doctrine: when there is only one way to express an idea,
 * the expression merges with the idea and is not copyrightable.
 */
public class Singleton_B {

    private static volatile Singleton_B uniqueInstance;
    private final String settingsFile;

    private Singleton_B() {
        this.settingsFile = "/opt/service/settings.yaml";
    }

    // Lazy initialization with double-check locking
    public static Singleton_B getUniqueInstance() {
        if (uniqueInstance == null) {
            synchronized (Singleton_B.class) {
                if (uniqueInstance == null) {
                    uniqueInstance = new Singleton_B();
                }
            }
        }
        return uniqueInstance;
    }

    public String getSettingsFile() {
        return settingsFile;
    }
}
