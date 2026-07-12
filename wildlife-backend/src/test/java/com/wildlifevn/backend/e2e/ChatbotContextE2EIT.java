package com.wildlifevn.backend.e2e;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.openqa.selenium.By;
import org.openqa.selenium.Dimension;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

class ChatbotContextE2EIT {

    private static final String FRONTEND_BASE_URL = System.getProperty(
            "frontend.baseUrl",
            System.getenv().getOrDefault("FRONTEND_BASE_URL", "http://localhost:5173"));

    @Test
    void comparisonTableRendersAndSessionIsScopedToTheTab() {
        WebDriver driver = new ChromeDriver(chromeOptions());
        try {
            driver.manage().window().setSize(new Dimension(1440, 1000));
            openChatAndSubmit(driver, "So sánh Công lục với Cá sấu Xiêm về bảo tồn");

            WebElement table = new WebDriverWait(driver, Duration.ofSeconds(20))
                    .until(ExpectedConditions.visibilityOfElementLocated(By.cssSelector(".chat-markdown table")));
            assertThat(table.getText()).contains("Công lục", "Cá sấu Xiêm", "Bảo tồn");

            JavascriptExecutor js = (JavascriptExecutor) driver;
            assertThat(js.executeScript("return sessionStorage.getItem('chatbot-session-id')"))
                    .isNotNull();
            assertThat(js.executeScript("return localStorage.getItem('chatbot-session-id')"))
                    .isNull();
        } finally {
            driver.quit();
        }
    }

    @Test
    void comparisonTableDoesNotCreatePageOverflowOnMobile() {
        WebDriver driver = new ChromeDriver(chromeOptions());
        try {
            driver.manage().window().setSize(new Dimension(390, 844));
            openChatAndSubmit(driver, "So sánh Công lục với Cá sấu Xiêm về bảo tồn");
            new WebDriverWait(driver, Duration.ofSeconds(20))
                    .until(ExpectedConditions.visibilityOfElementLocated(By.cssSelector(".chat-markdown table")));

            JavascriptExecutor js = (JavascriptExecutor) driver;
            long pageWidth = ((Number) js.executeScript("return document.documentElement.scrollWidth")).longValue();
            long viewportWidth = ((Number) js.executeScript("return window.innerWidth")).longValue();
            assertThat(pageWidth).isLessThanOrEqualTo(viewportWidth + 1);
        } finally {
            driver.quit();
        }
    }

    private static void openChatAndSubmit(WebDriver driver, String question) {
        WebDriverWait wait = new WebDriverWait(driver, Duration.ofSeconds(20));
        driver.get(FRONTEND_BASE_URL + "/qa");
        wait.until(ExpectedConditions.visibilityOfElementLocated(By.cssSelector("[data-testid='chatbot-page']")));
        WebElement input = wait.until(
                ExpectedConditions.elementToBeClickable(By.cssSelector("[data-testid='chatbot-input']")));
        input.sendKeys(question);
        driver.findElement(By.cssSelector("[data-testid='chatbot-send-button']")).click();
    }

    private static ChromeOptions chromeOptions() {
        ChromeOptions options = new ChromeOptions();
        options.addArguments(
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage");
        return options;
    }
}
